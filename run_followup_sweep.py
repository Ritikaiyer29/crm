"""
Batch sweep: finds every non-resolved ticket within AT_RISK_THRESHOLD_DAYS of
its regulatory deadline (or already past it) and proposes an escalation for
each, via the follow-up agent directly.

This calls check_and_propose_followup directly rather than going through the
router graph: the SQL filter below already knows exactly which agent this
batch needs (follow_up), so routing through the graph's "what does this
ticket need" dispatch would just be indirection with no benefit. The router
earns its keep at the single-ticket entry point instead (e.g. a future
webhook fired right after a ticket is created or updated), where the caller
genuinely doesn't know yet whether triage or follow-up applies.

This is what a scheduler (APScheduler/Celery, per the original architecture
plan) would call periodically; run directly for now.

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
from agents.follow_up_agent import AT_RISK_THRESHOLD_DAYS, check_and_propose_followup
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

        proposals = 0
        for ticket in at_risk_tickets:
            action = check_and_propose_followup(session, str(ticket.id))
            if action:
                proposals += 1
                print(f"  [{ticket.id}] {action.action_type} proposal written ({action.id})")

        skipped = len(at_risk_tickets) - proposals
        print(f"\nDone. {proposals} new follow-up proposals written to agent_actions "
              f"({skipped} skipped -- already had a pending proposal).")


if __name__ == "__main__":
    main()
