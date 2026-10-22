"""Staff inbox for conversations the chatbot handed over."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.auth import get_current_user
from api.schemas import AdminReplyIn, ConversationDetail, ConversationListItem, StaffMessageOut
from database import get_session
from models import AppUser, Conversation, ConversationStatus, Message, MessageRole

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _get_scoped(session: Session, conversation_id: uuid.UUID, user: AppUser) -> Conversation:
    conv = session.get(Conversation, conversation_id)
    if conv is None or conv.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


def _email(session: Session, user_id: Optional[uuid.UUID]) -> Optional[str]:
    if user_id is None:
        return None
    user = session.get(AppUser, user_id)
    return user.email if user else None


def _flags(conv: Conversation) -> list[str]:
    return list((conv.escalation_flags or {}).get("flags", []))


def _staff_message(session: Session, m: Message) -> StaffMessageOut:
    return StaffMessageOut(
        id=m.id, seq=m.seq, role=m.role.value, content=m.content, citations=m.citations,
        created_at=m.created_at, author_email=_email(session, m.author_id),
    )


@router.get("", response_model=list[ConversationListItem])
def list_conversations(
    status_filter: Optional[str] = Query("escalated", alias="status"),
    limit: int = Query(50, le=100),
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> list[ConversationListItem]:
    query = select(Conversation).where(Conversation.org_id == current_user.org_id)
    if status_filter and status_filter != "all":
        try:
            query = query.where(Conversation.status == ConversationStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status_filter!r}")
    convs = session.scalars(query.order_by(Conversation.last_message_at.desc()).offset(offset).limit(limit)).all()

    items: list[ConversationListItem] = []
    for c in convs:
        last = session.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.seq.desc()).limit(1)).first()
        count = session.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == c.id)) or 0
        items.append(
            ConversationListItem(
                id=c.id, status=c.status.value, escalation_reason=c.escalation_reason, flags=_flags(c), summary=c.summary,
                last_message_preview=(last.content[:140] if last else ""), last_message_role=(last.role.value if last else "customer"),
                message_count=count, last_message_at=c.last_message_at, escalated_at=c.escalated_at,
                assigned_to_email=_email(session, c.assigned_to),
            )
        )
    return items


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> ConversationDetail:
    c = _get_scoped(session, conversation_id, current_user)
    msgs = session.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.seq)).all()
    return ConversationDetail(
        id=c.id, status=c.status.value, escalation_reason=c.escalation_reason, flags=_flags(c), summary=c.summary,
        draft_reply=c.draft_reply, assigned_to_email=_email(session, c.assigned_to), created_at=c.created_at,
        escalated_at=c.escalated_at, resolved_at=c.resolved_at, messages=[_staff_message(session, m) for m in msgs],
    )


@router.post("/{conversation_id}/reply", response_model=StaffMessageOut)
def reply(
    conversation_id: uuid.UUID,
    body: AdminReplyIn,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> StaffMessageOut:
    c = _get_scoped(session, conversation_id, current_user)
    text = body.content.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Reply is empty")

    message = Message(conversation_id=c.id, role=MessageRole.admin, content=text, author_id=current_user.id)
    session.add(message)
    now = datetime.now(timezone.utc)
    if c.status != ConversationStatus.escalated:
        # A person stepping in takes the conversation over from the bot, or reopens a resolved one.
        c.status = ConversationStatus.escalated
        c.escalated_at = c.escalated_at or now
        c.escalation_reason = c.escalation_reason or "Staff joined the conversation"
        c.resolved_at = None
    c.assigned_to = current_user.id
    c.draft_reply = None
    c.last_message_at = c.updated_at = now
    session.commit()
    session.refresh(message)
    return _staff_message(session, message)


@router.post("/{conversation_id}/resolve", response_model=ConversationDetail)
def resolve(
    conversation_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> ConversationDetail:
    c = _get_scoped(session, conversation_id, current_user)
    if c.status != ConversationStatus.resolved:
        now = datetime.now(timezone.utc)
        session.add(
            Message(
                conversation_id=c.id, role=MessageRole.system,
                content="A team member marked this conversation as resolved. Send a message if you need more help.",
                author_id=current_user.id,
            )
        )
        c.status = ConversationStatus.resolved
        c.resolved_at = now
        c.assigned_to = c.assigned_to or current_user.id
        c.last_message_at = c.updated_at = now
        session.commit()
    return get_conversation(conversation_id, session, current_user)
