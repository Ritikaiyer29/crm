from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import get_current_user
from api.schemas import AgentActionOut, EditActionRequest
from approval import NoMatchedCategoryError, approve_action, edit_text_action, edit_triage_action, reject_action
from database import get_session
from models import AgentAction, ApprovalStatus, AppUser, Contact, Deal, Ticket

router = APIRouter(prefix="/agent-actions", tags=["agent_actions"])


def action_out(session: Session, action: AgentAction) -> AgentActionOut:
    ticket_narrative = None
    contact_name = None
    if action.ticket_id:
        ticket = session.get(Ticket, action.ticket_id)
        ticket_narrative = ticket.narrative if ticket else None
    elif action.deal_id:
        deal = session.get(Deal, action.deal_id)
        if deal:
            contact = session.get(Contact, deal.contact_id)
            contact_name = contact.full_name if contact else None

    proposed_category_id = None
    proposed_priority = None
    if action.agent_name == "triage" and action.tool_calls:
        proposed_category_id = action.tool_calls.get("matched_category_id")
        proposed_priority = action.tool_calls.get("proposed_priority")

    return AgentActionOut(
        id=action.id,
        agent_name=action.agent_name,
        action_type=action.action_type,
        input_summary=action.input_summary,
        proposed_output=action.proposed_output,
        final_output=action.final_output,
        confidence=action.confidence,
        approval_status=action.approval_status.value,
        created_at=action.created_at,
        ticket_id=action.ticket_id,
        deal_id=action.deal_id,
        ticket_narrative=ticket_narrative,
        contact_name=contact_name,
        proposed_category_id=proposed_category_id,
        proposed_priority=proposed_priority,
    )


def _get_scoped_action(session: Session, action_id: str, current_user: AppUser) -> AgentAction:
    action = session.get(AgentAction, action_id)
    if action is None or action.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Agent action not found")
    return action


@router.get("", response_model=list[AgentActionOut])
def list_agent_actions(
    status_filter: Optional[str] = Query("pending", alias="status"),
    agent_name: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> list[AgentActionOut]:
    query = select(AgentAction).where(AgentAction.org_id == current_user.org_id)
    if status_filter:
        try:
            query = query.where(AgentAction.approval_status == ApprovalStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status_filter!r}")
    if agent_name:
        query = query.where(AgentAction.agent_name == agent_name)
    query = query.order_by(AgentAction.created_at).offset(offset).limit(limit)
    actions = session.scalars(query).all()
    return [action_out(session, a) for a in actions]


@router.post("/{action_id}/approve", response_model=AgentActionOut)
def approve(
    action_id: str,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> AgentActionOut:
    action = _get_scoped_action(session, action_id, current_user)
    if action.approval_status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail=f"Action is already {action.approval_status.value}")
    try:
        approve_action(session, action, approved_by=current_user.id)
    except NoMatchedCategoryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return action_out(session, action)


@router.post("/{action_id}/reject", response_model=AgentActionOut)
def reject(
    action_id: str,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> AgentActionOut:
    action = _get_scoped_action(session, action_id, current_user)
    if action.approval_status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail=f"Action is already {action.approval_status.value}")
    reject_action(session, action, approved_by=current_user.id)
    return action_out(session, action)


@router.post("/{action_id}/edit", response_model=AgentActionOut)
def edit(
    action_id: str,
    body: EditActionRequest,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> AgentActionOut:
    action = _get_scoped_action(session, action_id, current_user)
    if action.approval_status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail=f"Action is already {action.approval_status.value}")

    if action.agent_name == "triage":
        if body.category_id is None or body.priority is None:
            raise HTTPException(status_code=400, detail="triage edits require category_id and priority")
        edit_triage_action(session, action, str(body.category_id), body.priority, approved_by=current_user.id)
    else:
        if body.text is None:
            raise HTTPException(status_code=400, detail="non-triage edits require text")
        edit_text_action(session, action, body.text, approved_by=current_user.id)
    return action_out(session, action)
