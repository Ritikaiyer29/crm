"""
Runs one customer message through the chat graph and stores the result.

The customer's message is committed before the graph runs, so it is never lost
if something fails. If the model call fails (quota, outage), the conversation
is handed to a person rather than left without an answer.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.chat_graph import build_chat_graph
from agents.pii import redact_text
from models import Conversation, ConversationStatus, Message, MessageRole

HISTORY_WINDOW = 8
ERROR_HANDOFF_REASON = "Assistant was unavailable"
ERROR_REPLY = (
    "I'm having trouble answering right now, so I've passed this to a team member. "
    "They will reply right here in this chat."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _history(session: Session, conversation_id, exclude_seq: int) -> list[dict]:
    rows = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.seq < exclude_seq, Message.role != MessageRole.system)
        .order_by(Message.seq.desc())
        .limit(HISTORY_WINDOW)
    ).all()
    return [{"role": m.role.value, "text": redact_text(m.content)} for m in reversed(rows)]


def _escalate(conv: Conversation, reason: str, flags: list[str], summary: str | None, draft: str | None) -> None:
    conv.status = ConversationStatus.escalated
    conv.escalated_at = _now()
    conv.escalation_reason = reason
    conv.escalation_flags = {"flags": flags}
    conv.summary = summary
    conv.draft_reply = draft or None


def handle_customer_message(session: Session, conv: Conversation, text: str) -> list[Message]:
    """Stores the customer's message, runs the bot unless a person already has the conversation, and
    returns the messages created by this call (customer message first)."""
    if conv.status == ConversationStatus.resolved:
        conv.status = ConversationStatus.bot
        conv.resolved_at = None

    customer_msg = Message(conversation_id=conv.id, role=MessageRole.customer, content=text)
    session.add(customer_msg)
    conv.last_message_at = conv.updated_at = _now()
    session.commit()
    session.refresh(customer_msg)

    if conv.status == ConversationStatus.escalated:
        return [customer_msg]

    history = _history(session, conv.id, customer_msg.seq)
    try:
        out = build_chat_graph(session, conv.org_id).invoke(
            {"message": redact_text(text), "history": history, "meta": {}, "fallbacks": (conv.state or {}).get("fallbacks", 0)}
        )
        reply, citations, handoff = out["reply"], out.get("citations") or None, out.get("handoff")
        meta = {"understanding": out.get("understanding"), "decision": out.get("decision"), **(out.get("meta") or {})}
    except Exception as exc:  # noqa: BLE001 - never leave the customer without a response
        session.rollback()
        conv = session.get(Conversation, conv.id)
        reply, citations, meta = ERROR_REPLY, None, {"error": type(exc).__name__}
        handoff = {"reason": ERROR_HANDOFF_REASON, "flags": ["assistant_error"], "summary": f"{ERROR_HANDOFF_REASON}. Latest message: {text[:300]}", "draft_reply": ""}

    bot_msg = Message(conversation_id=conv.id, role=MessageRole.bot, content=reply, citations=citations, meta=meta)
    session.add(bot_msg)
    conv.state = {**(conv.state or {}), "fallbacks": (conv.state or {}).get("fallbacks", 0) + 1 if meta.get("fallback") else 0}
    if handoff:
        _escalate(conv, handoff["reason"], handoff["flags"], handoff["summary"], handoff["draft_reply"])
    conv.last_message_at = conv.updated_at = _now()
    session.commit()
    session.refresh(bot_msg)
    return [customer_msg, bot_msg]
