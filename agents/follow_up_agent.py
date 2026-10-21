"""
Follow-up agent: watches each ticket's 30-day regulatory deadline
(Ticket.regulatory_deadline, set by schema.sql's trigger) and proposes an
escalation when a ticket is at risk of breaching it or already has.

The urgency decision itself is deterministic, not LLM-judged: whether a
ticket is 3 days from its regulatory deadline is a fact, not something to
ask a language model to assess, and getting it wrong has real regulatory
consequences (RB-IOS 2026 lets the customer escalate straight to the RBI
Ombudsman once day 30 passes without a reply). The LLM's job is narrower and
safer: draft the internal escalation note's wording once the deterministic
check has already decided escalation is warranted.

Like the triage agent, this only ever writes a *proposal* to agent_actions
(approval_status='pending') -- it never changes Ticket.status itself.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from sqlalchemy import select
from sqlalchemy.orm import Session

load_dotenv()
from models import AgentAction, ApprovalStatus, Ticket, TicketStatus

GROQ_MODEL = "openai/gpt-oss-120b"
AT_RISK_THRESHOLD_DAYS = 5  # propose a warning once this close to the deadline


def _build_llm() -> ChatGroq:
    return ChatGroq(model=GROQ_MODEL, temperature=0.3, api_key=os.environ["GROQ_API_KEY"])


def check_and_propose_followup(session: Session, ticket_id: str) -> AgentAction | None:
    """Returns the created AgentAction, or None if this ticket doesn't need
    follow-up right now (not close to its deadline, already resolved, or a
    proposal for it is already sitting in the approval queue)."""
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} not found")

    if ticket.status == TicketStatus.resolved or ticket.regulatory_deadline is None:
        return None

    days_remaining = (ticket.regulatory_deadline - datetime.now(timezone.utc)).days
    if days_remaining > AT_RISK_THRESHOLD_DAYS:
        return None  # plenty of time -- nothing for this agent to do

    # Avoid flooding the approval queue: a daily sweep would otherwise write
    # a fresh proposal for the same still-pending ticket every single run.
    existing_pending = session.scalar(
        select(AgentAction).where(
            AgentAction.ticket_id == ticket.id,
            AgentAction.agent_name == "follow_up",
            AgentAction.approval_status == ApprovalStatus.pending,
        )
    )
    if existing_pending is not None:
        return None

    overdue = days_remaining < 0
    urgency = (
        "OVERDUE -- past the RBI RB-IOS 2026 30-day deadline"
        if overdue
        else f"AT RISK -- {days_remaining} day(s) left before the RBI RB-IOS 2026 30-day deadline"
    )

    llm = _build_llm()
    prompt = (
        "You are a follow-up agent for an Indian bank's complaint CRM. Draft a short, "
        "specific internal escalation note (2-3 sentences, addressed to the complaint-"
        "handling team, not the customer) for the ticket below.\n\n"
        f"Status: {urgency}\n"
        f"Ticket status: {ticket.status.value}\n"
        f"Ticket priority: {ticket.priority.value}\n"
        f"Complaint narrative: \"{ticket.narrative}\"\n\n"
        "State plainly what needs to happen next and why it's urgent. If overdue, mention "
        "that the customer is now entitled to escalate directly to the RBI Ombudsman."
    )
    note = llm.invoke(prompt).content

    action = AgentAction(
        org_id=ticket.org_id,
        ticket_id=ticket.id,
        agent_name="follow_up",
        action_type="escalate" if overdue else "escalation_warning",
        input_summary=f"{urgency}; ticket status={ticket.status.value}",
        proposed_output=note,
        tool_calls={
            "model": GROQ_MODEL,
            "regulatory_deadline": ticket.regulatory_deadline.isoformat(),
            "days_remaining": days_remaining,
        },
        confidence=Decimal("1.000"),  # the deadline check is deterministic, not a model guess
        requires_approval=True,
        approval_status=ApprovalStatus.pending,
    )
    session.add(action)
    session.commit()
    return action
