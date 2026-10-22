"""Customer-facing chat endpoints. No login: the conversation id (a random UUID) is the only credential,
the same way a complaint reference number is."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.chat_service import handle_customer_message
from api.ratelimit import RateLimiter
from api.schemas import ChatMessageIn, ChatMessageOut, ChatPollOut, ChatReplyOut
from database import get_session
from models import Conversation, Message, MessageRole, Org

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_CUSTOMER_MESSAGES = 60

_post_per_minute = RateLimiter("chat-post-minute", calls=12, per_seconds=60)
_post_per_hour = RateLimiter("chat-post-hour", calls=120, per_seconds=3600)
_poll_per_minute = RateLimiter("chat-poll", calls=60, per_seconds=60)


def _out(m: Message) -> ChatMessageOut:
    return ChatMessageOut(id=m.id, seq=m.seq, role=m.role.value, content=m.content, citations=m.citations, created_at=m.created_at)


@router.post("/messages", response_model=ChatReplyOut, dependencies=[Depends(_post_per_minute), Depends(_post_per_hour)])
def send_message(payload: ChatMessageIn, session: Session = Depends(get_session)) -> ChatReplyOut:
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message is empty")

    if payload.conversation_id:
        conv = session.get(Conversation, payload.conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        sent = session.scalar(
            select(func.count()).select_from(Message).where(Message.conversation_id == conv.id, Message.role == MessageRole.customer)
        )
        if sent >= MAX_CUSTOMER_MESSAGES:
            raise HTTPException(status_code=429, detail="This conversation is full. Please start a new chat.")
    else:
        org = session.scalars(select(Org)).first()
        if org is None:
            raise HTTPException(status_code=503, detail="No organization configured yet")
        conv = Conversation(org_id=org.id)
        session.add(conv)
        session.commit()
        session.refresh(conv)

    messages = handle_customer_message(session, conv, text)
    session.refresh(conv)
    return ChatReplyOut(conversation_id=conv.id, status=conv.status.value, messages=[_out(m) for m in messages])


@router.get("/conversations/{conversation_id}/messages", response_model=ChatPollOut, dependencies=[Depends(_poll_per_minute)])
def poll_messages(
    conversation_id: uuid.UUID,
    after_seq: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> ChatPollOut:
    conv = session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = session.scalars(
        select(Message).where(Message.conversation_id == conv.id, Message.seq > after_seq).order_by(Message.seq)
    ).all()
    return ChatPollOut(status=conv.status.value, messages=[_out(m) for m in rows])
