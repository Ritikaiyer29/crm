"""
Batch sweep: finds every non-resolved ticket within AT_RISK_THRESHOLD_DAYS of
its regulatory deadline (or already past it) and proposes an escalation for
each, via the follow-up agent directly.

Each ticket goes through the LangGraph router (agents/graph.py) rather than
straight to the follow-up agent. The SQL filter only narrows the batch to
at-risk tickets (within 5 days of the deadline); the router still decides what
each one needs. That is nearly always follow-up. A customer ticket whose
auto-triage failed would only reach the router here around day 25.

This is what a scheduler (Cloud Scheduler, see DEPLOY.md) calls
periodically; run directly otherwise.

Usage:
    python run_followup_sweep.py            # every at-risk/overdue ticket
    python run_followup_sweep.py --limit 5   # just the first 5 (cheap smoke test)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

load_dotenv()
from agents.follow_up_agent import AT_RISK_THRESHOLD_DAYS
from agents.graph import build_graph
from models import Ticket, TicketStatus

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="only process the first N at-risk tickets")
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        cutoff = datetime.now(timezone.utc) + timedelta(days=AT_RISK_THRESHOLD_DAYS)
        query = select(Ticket).where(
            Ticket.status != TicketStatus.resolved,
            Ticket.regulatory_deadline <= cutoff,
        )
        if args.limit:
            query = query.limit(args.limit)
        at_risk_tickets = session.scalars(query).all()
        print(
            f"Found {len(at_risk_tickets)} non-resolved tickets within "
            f"{AT_RISK_THRESHOLD_DAYS} days of (or past) their regulatory deadline."
        )

        graph = build_graph(session)
        proposals = 0
        for ticket in at_risk_tickets:
            state = graph.invoke({"ticket_id": str(ticket.id), "route": None, "agent_action_id": None})
            if state["agent_action_id"]:
                proposals += 1
                print(f"  [{ticket.id}] routed to {state['route']}: proposal written ({state['agent_action_id']})")

        skipped = len(at_risk_tickets) - proposals
        print(f"\nDone. {proposals} new proposals written to agent_actions "
              f"({skipped} skipped -- already had a pending proposal).")


if __name__ == "__main__":
    main()
