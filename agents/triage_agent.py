"""
Triage agent: classifies a ticket's narrative into one of the org's real
grievance categories, plus a priority, using Groq.

Every call is a *proposal*, never a direct write to the ticket. The result
goes into agent_actions with approval_status='pending' and
requires_approval=True -- Ticket.category_id/priority are not touched here.
That split (propose vs. apply) is what makes the human-approval gate
(Phase 6) meaningful rather than decorative: turning a pending row into a
real ticket update is a separate, explicit step a human takes.

classify_ticket() and run_triage() are deliberately separate: run_triage()
(production path) classifies AND persists a pending agent_actions row.
classify_ticket() (used by run_eval.py) does only the classification, with
no DB write -- an eval pass over hundreds of tickets has no business
creating hundreds of phantom "pending approval" rows that would sit in the
review queue forever, mixed in with real proposals a human is actually
meant to act on.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

load_dotenv()
from agents.pii import redact_text
from models import AgentAction, ApprovalStatus, GrievanceCategory, Ticket

# Groq's hosted model catalog turns over: as of this writing it no longer
# serves any Llama models at all, only openai/gpt-oss-*, qwen/*, allam-2-7b,
# and audio/guard models (checked live via client.models.list(), not assumed).
# gpt-oss-120b is the strongest available and supports tool-calling (needed
# for structured output) -- classification accuracy matters more here than
# shaving latency, and Groq's inference is fast regardless of model size.
GROQ_MODEL = "openai/gpt-oss-120b"


class TriageResult(BaseModel):
    category_name: str = Field(description="Must be exactly one of the provided category names, verbatim.")
    priority: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="One or two sentences on why this category and priority.")


@dataclass
class Classification:
    result: TriageResult
    matched: Optional[GrievanceCategory]  # None if the LLM's category_name matched nothing real
    confidence: float  # 0.0 if matched is None, regardless of what the model claimed
    category_names: list[str]  # the option list offered to the model, for logging/audit


def _build_llm(model: str = GROQ_MODEL, api_key: Optional[str] = None) -> ChatGroq:
    return ChatGroq(model=model, temperature=0, api_key=api_key or os.environ["GROQ_API_KEY"])


def classify_ticket(
    session: Session, ticket: Ticket, model: str = GROQ_MODEL, api_key: Optional[str] = None
) -> Classification:
    # model and api_key are overridable (used by run_eval.py to compare
    # models and to rotate between multiple Groq API keys once the active
    # one hits its daily quota -- Groq tracks both rate limits and model
    # availability per-model and per-key independently).
    categories = session.scalars(select(GrievanceCategory)).all()
    category_names = [c.category_name for c in categories]

    structured_llm = _build_llm(model, api_key).with_structured_output(TriageResult)
    prompt = (
        "You are a triage agent for an Indian bank's customer complaint CRM.\n"
        "Classify the complaint below into EXACTLY ONE of these categories "
        "(copy the name verbatim -- do not paraphrase or invent a new one):\n"
        + "\n".join(f"- {name}" for name in category_names)
        + f"\n\nComplaint narrative:\n\"\"\"\n{redact_text(ticket.narrative)}\n\"\"\"\n\n"
        "Also assign a priority (low/medium/high/critical) based on financial "
        "harm, urgency, and whether the customer describes fraud or an "
        "unauthorised transaction."
    )
    result: TriageResult = structured_llm.invoke(prompt)

    # The LLM is asked to copy a category name verbatim, but nothing stops it
    # from paraphrasing anyway -- so we verify the match ourselves rather than
    # trusting the string blindly. A miss forces confidence to 0, which is a
    # real signal to whoever reviews this in the approval queue (or, in eval,
    # a real miss rather than a name-formatting false negative).
    matched = next(
        (c for c in categories if c.category_name.lower() == result.category_name.lower()),
        None,
    )
    return Classification(
        result=result,
        matched=matched,
        confidence=result.confidence if matched else 0.0,
        category_names=category_names,
    )


def run_triage(session: Session, ticket_id: str) -> AgentAction:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id} not found")

    classification = classify_ticket(session, ticket)
    result, matched, confidence = classification.result, classification.matched, classification.confidence
    match_note = f"matched: {matched.category_name}" if matched else "NO MATCH to known categories"

    action = AgentAction(
        org_id=ticket.org_id,
        ticket_id=ticket.id,
        agent_name="triage",
        action_type="classify",
        input_summary=ticket.narrative[:500],
        proposed_output=(
            f"category={result.category_name!r} ({match_note}), "
            f"priority={result.priority}, reasoning={result.reasoning}"
        ),
        tool_calls={
            "model": GROQ_MODEL,
            "category_options": classification.category_names,
            # The approval step applies these directly to Ticket.category_id/
            # priority rather than re-parsing proposed_output's prose -- that
            # string is for a human to read, not to round-trip through.
            "matched_category_id": str(matched.id) if matched else None,
            "proposed_priority": result.priority,
        },
        confidence=Decimal(str(round(confidence, 3))),
        requires_approval=True,
        approval_status=ApprovalStatus.pending,
    )
    session.add(action)
    session.commit()
    return action
