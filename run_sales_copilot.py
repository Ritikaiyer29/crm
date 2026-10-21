"""
Runs the sales copilot agent against every 'identified'-stage deal, drafting
a next-action recommendation for the relationship management team.

Usage:
    python run_sales_copilot.py            # all identified-stage deals
    python run_sales_copilot.py --limit 5  # just the first 5 (cheap smoke test)
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

load_dotenv()
from agents.sales_copilot_agent import propose_next_action
from models import AgentAction, Deal, DealStage

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="only process the first N deals")
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        query = select(Deal).where(Deal.stage == DealStage.identified)
        if args.limit:
            query = query.limit(args.limit)
        deals = session.scalars(query).all()
        print(f"Processing {len(deals)} identified-stage deals...")

        proposals = 0
        for deal in deals:
            existing = session.scalar(
                select(AgentAction).where(
                    AgentAction.deal_id == deal.id,
                    AgentAction.agent_name == "sales_copilot",
                )
            )
            if existing:
                continue
            action = propose_next_action(session, str(deal.id))
            proposals += 1
            print(f"  [{deal.contact.full_name}] {deal.type.value}: {action.proposed_output[:140]}...")

        skipped = len(deals) - proposals
        print(f"\nDone. {proposals} new sales copilot proposals written "
              f"({skipped} skipped -- already had a proposal).")


if __name__ == "__main__":
    main()
