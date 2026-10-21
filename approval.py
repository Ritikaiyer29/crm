"""
Shared approval-application logic: turning an approved/edited agent_actions
proposal into the real write it describes. This is used by both
review_actions.py (the CLI) and the FastAPI approval routes (api/routers/
agent_actions.py) -- there is exactly one place this logic lives, so the two
interfaces can never silently diverge on what "approved" actually does to a
ticket or deal.

Each agent's apply_* function mirrors the decision already made back when
that agent's proposal was first written (see agents/triage_agent.py,
agents/follow_up_agent.py, agents/sales_copilot_agent.py for why each one
does what it does) -- this module is only the "turn it into a real write"
half, not where those decisions are made.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models import AgentAction, ApprovalStatus, Deal, DealStage, Ticket, TicketPriority, TicketStatus


class NoMatchedCategoryError(Exception):
    """Raised when approving a triage action that predates matched_category_id
    being recorded (see agents/triage_agent.py) -- there's nothing to apply
    without an explicit edit supplying a category."""


def apply_triage(session: Session, action: AgentAction, category_id: str, priority: str) -> None:
    ticket = session.get(Ticket, action.ticket_id)
    ticket.category_id = category_id
    ticket.priority = TicketPriority(priority)


def apply_follow_up(session: Session, action: AgentAction) -> None:
    if action.action_type == "escalate":
        ticket = session.get(Ticket, action.ticket_id)
        ticket.status = TicketStatus.escalated
    # escalation_warning has nothing structural to apply -- approving it just
    # means "a human has seen this and will handle it," which the
    # approval_status change itself already records.


def apply_sales_copilot(session: Session, action: AgentAction) -> None:
    deal = session.get(Deal, action.deal_id)
    deal.stage = DealStage.in_progress


def approve_action(session: Session, action: AgentAction, approved_by: Optional[uuid.UUID] = None) -> None:
    if action.agent_name == "triage":
        category_id = action.tool_calls.get("matched_category_id") if action.tool_calls else None
        priority = action.tool_calls.get("proposed_priority") if action.tool_calls else None
        if category_id is None:
            raise NoMatchedCategoryError("No matched category recorded -- edit instead of approve.")
        apply_triage(session, action, category_id, priority)
    elif action.agent_name == "follow_up":
        apply_follow_up(session, action)
    elif action.agent_name == "sales_copilot":
        apply_sales_copilot(session, action)

    action.approval_status = ApprovalStatus.approved
    action.final_output = action.proposed_output
    action.approved_by = approved_by
    action.resolved_at = datetime.now(timezone.utc)
    session.commit()


def reject_action(session: Session, action: AgentAction, approved_by: Optional[uuid.UUID] = None) -> None:
    action.approval_status = ApprovalStatus.rejected
    action.approved_by = approved_by
    action.resolved_at = datetime.now(timezone.utc)
    session.commit()


def edit_triage_action(
    session: Session,
    action: AgentAction,
    category_id: str,
    priority: str,
    approved_by: Optional[uuid.UUID] = None,
) -> None:
    apply_triage(session, action, category_id, priority)
    action.final_output = f"[edited] category_id={category_id}, priority={priority}"
    action.approval_status = ApprovalStatus.edited
    action.approved_by = approved_by
    action.resolved_at = datetime.now(timezone.utc)
    session.commit()


def edit_text_action(
    session: Session,
    action: AgentAction,
    new_text: str,
    approved_by: Optional[uuid.UUID] = None,
) -> None:
    if action.agent_name == "follow_up":
        apply_follow_up(session, action)
    elif action.agent_name == "sales_copilot":
        apply_sales_copilot(session, action)
    action.final_output = new_text
    action.approval_status = ApprovalStatus.edited
    action.approved_by = approved_by
    action.resolved_at = datetime.now(timezone.utc)
    session.commit()
