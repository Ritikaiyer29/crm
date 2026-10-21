"""
The human-approval gate: an interactive CLI that lists pending agent_actions
one at a time and lets a reviewer approve, reject, edit, or skip each one.

This is the piece that makes the "mandatory human-approval gate" more than a
slogan: every agent so far (triage, follow_up, sales_copilot) only ever
writes a *proposal* with approval_status='pending'. Nothing in tickets or
deals has changed yet. This script is where a pending proposal either gets
discarded, or turns into a real write -- and that real write only happens
here, in one place, so it's always clear where the line between "agent
suggested" and "system changed" is crossed.

No auth/app_users exist yet (that's Phase 8), so AgentAction.approved_by is
left null for now -- there's no real reviewer identity to attach yet.

Usage:
    python review_actions.py                  # review all pending, oldest first
    python review_actions.py --agent triage    # only one agent's proposals
    python review_actions.py --limit 10        # cap the session length
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

load_dotenv()
from approval import NoMatchedCategoryError, approve_action, edit_triage_action, edit_text_action, reject_action
from models import AgentAction, ApprovalStatus, Contact, Deal, GrievanceCategory, Ticket, TicketPriority

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

PRIORITY_CHOICES = [p.value for p in TicketPriority]


def _print_context(session: Session, action: AgentAction) -> None:
    print(f"\n{'=' * 70}")
    print(f"[{action.agent_name}] {action.action_type}  (confidence: {action.confidence})")
    print(f"agent_action_id: {action.id}")

    if action.ticket_id:
        ticket = session.get(Ticket, action.ticket_id)
        current_category = session.get(GrievanceCategory, ticket.category_id)
        print(f"Ticket:   {ticket.narrative}")
        print(f"Current:  category={current_category.category_name!r}, "
              f"priority={ticket.priority.value}, status={ticket.status.value}")
    elif action.deal_id:
        deal = session.get(Deal, action.deal_id)
        contact = session.get(Contact, deal.contact_id)
        print(f"Contact:  {contact.full_name}  |  Deal: {deal.type.value} ({deal.stage.value})")
        print(f"Notes:    {deal.notes}")

    print(f"\nProposed: {action.proposed_output}")
    print(f"{'=' * 70}")


def _edit_triage(session: Session, action: AgentAction) -> tuple[str, str] | None:
    categories = session.scalars(select(GrievanceCategory).order_by(GrievanceCategory.category_name)).all()
    for i, c in enumerate(categories, start=1):
        print(f"  {i:2d}. {c.category_name}")
    raw = input(f"Pick a category number (blank = keep proposed): ").strip()
    if raw:
        try:
            category_id = str(categories[int(raw) - 1].id)
        except (ValueError, IndexError):
            print("Invalid choice, aborting edit.")
            return None
    else:
        category_id = action.tool_calls.get("matched_category_id") if action.tool_calls else None
        if category_id is None:
            print("No proposed category on file -- you must pick one.")
            return None

    raw = input(f"Priority {PRIORITY_CHOICES} (blank = keep proposed): ").strip().lower()
    if raw:
        if raw not in PRIORITY_CHOICES:
            print("Invalid priority, aborting edit.")
            return None
        priority = raw
    else:
        priority = action.tool_calls.get("proposed_priority") if action.tool_calls else None
        if priority is None:
            print("No proposed priority on file -- you must pick one.")
            return None

    return category_id, priority


def review_one(session: Session, action: AgentAction) -> str:
    """Returns 'quit' to stop the session, otherwise the decision made."""
    _print_context(session, action)
    choice = input("[a]pprove  [r]eject  [e]dit  [s]kip  [q]uit > ").strip().lower()

    if choice == "q":
        return "quit"

    if choice == "s":
        return "skipped"

    if choice == "r":
        reject_action(session, action)
        return "rejected"

    if choice == "a":
        try:
            approve_action(session, action)
        except NoMatchedCategoryError:
            print("This proposal has no matched category recorded (likely predates this "
                  "field) -- use [e]dit instead.")
            return "skipped"
        return "approved"

    if choice == "e":
        if action.agent_name == "triage":
            edited = _edit_triage(session, action)
            if edited is None:
                return "skipped"
            category_id, priority = edited
            edit_triage_action(session, action, category_id, priority)
        else:
            new_text = input("New text (blank = keep proposed): ").strip()
            edit_text_action(session, action, new_text or action.proposed_output)
        return "edited"

    print("Unrecognized input, treating as skip.")
    return "skipped"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=["triage", "follow_up", "sales_copilot"], default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        query = select(AgentAction).where(AgentAction.approval_status == ApprovalStatus.pending)
        if args.agent:
            query = query.where(AgentAction.agent_name == args.agent)
        query = query.order_by(AgentAction.created_at)
        if args.limit:
            query = query.limit(args.limit)
        pending = session.scalars(query).all()

        print(f"{len(pending)} pending proposals to review.")
        tally: dict[str, int] = {}
        for action in pending:
            result = review_one(session, action)
            if result == "quit":
                break
            tally[result] = tally.get(result, 0) + 1

        print(f"\nSession summary: {tally}")


if __name__ == "__main__":
    main()
