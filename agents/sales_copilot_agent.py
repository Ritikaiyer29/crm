"""
Sales copilot agent: reads a contact's ticket/deal history and drafts a
recommended next action for retention-risk or cross-sell deals.

This is contact-keyed, not ticket-keyed -- deliberately NOT a branch of the
ticket-lifecycle router in agents/graph.py. That router's state is built
around a single ticket_id because triage and follow-up are both facts about
one ticket's lifecycle. A deal, though, belongs to a contact and is informed
by their whole ticket history, not one ticket -- forcing it into the same
ticket-keyed state would mean stretching that shape to cover two different
entities for no real benefit. It gets its own entry point instead (see
run_sales_copilot.py).

Deals today come from seed_data.py's simple heuristic (an escalated ticket
-> retention_risk; an all-resolved history -> cross_sell); in the live
system they'd come from real ticket-outcome triggers, but this agent's job
is the same either way: given a flagged deal, propose what the relationship
manager should do about it.
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Literal

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

load_dotenv()
from models import AgentAction, ApprovalStatus, Deal, DealType, Ticket

GROQ_MODEL = "openai/gpt-oss-120b"


class SalesCopilotResult(BaseModel):
    recommended_action: str = Field(description="One concrete next action for the relationship manager to take.")
    talking_points: str = Field(description="2-3 sentences the RM can use when reaching out.")
    urgency: Literal["low", "medium", "high"]
    confidence: float = Field(ge=0.0, le=1.0)


def _build_llm() -> ChatGroq:
    return ChatGroq(model=GROQ_MODEL, temperature=0.3, api_key=os.environ["GROQ_API_KEY"])


def propose_next_action(session: Session, deal_id: str) -> AgentAction:
    deal = session.get(Deal, deal_id)
    if deal is None:
        raise ValueError(f"Deal {deal_id} not found")

    contact = deal.contact
    tickets = session.scalars(
        select(Ticket)
        .where(Ticket.contact_id == contact.id)
        .order_by(Ticket.date_received.desc())
        .limit(5)
    ).all()
    ticket_summary = (
        "\n".join(
            f"- [{t.date_received.date()}] {t.status.value}/{t.priority.value}: {t.narrative}"
            for t in tickets
        )
        or "No ticket history."
    )

    deal_kind = (
        "a customer at risk of leaving the bank"
        if deal.type == DealType.retention_risk
        else "a customer with a clean resolution history who may be receptive to another product"
    )

    structured_llm = _build_llm().with_structured_output(SalesCopilotResult)
    prompt = (
        "You are a sales copilot for an Indian bank's relationship management team.\n"
        f"This deal concerns {deal_kind}.\n"
        f"Deal notes: {deal.notes}\n\n"
        f"Contact's recent ticket history:\n{ticket_summary}\n\n"
        "Recommend one concrete next action for the relationship manager, with brief "
        "talking points, and how urgent this is."
    )
    result: SalesCopilotResult = structured_llm.invoke(prompt)

    action = AgentAction(
        org_id=deal.org_id,
        deal_id=deal.id,
        agent_name="sales_copilot",
        action_type="suggest_retention_offer" if deal.type == DealType.retention_risk else "suggest_cross_sell",
        input_summary=f"contact={contact.full_name}, deal_type={deal.type.value}, notes={deal.notes}",
        proposed_output=f"{result.recommended_action} | Talking points: {result.talking_points}",
        tool_calls={"model": GROQ_MODEL, "ticket_count_considered": len(tickets)},
        confidence=Decimal(str(round(result.confidence, 3))),
        requires_approval=True,
        approval_status=ApprovalStatus.pending,
    )
    session.add(action)
    session.commit()
    return action
