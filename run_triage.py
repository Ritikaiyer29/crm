"""
Runs the triage agent, via the LangGraph router, against a real seeded
ticket -- end to end against Supabase, printing the LLM's guess next to the
seeded (ground-truth) category so you can eyeball accuracy before Phase 7's
formal eval harness exists.

Usage:
    python run_triage.py <ticket_id>
    python run_triage.py --random
"""
from __future__ import annotations

import argparse
import os
import sys

# Windows consoles default stdout to the system codepage (cp1252), which
# can't encode characters an LLM routinely generates (curly quotes, non-
# breaking hyphens, rupee signs) -- a bare print() of that text crashes with
# UnicodeEncodeError. The data itself is stored fine as UTF-8 in Postgres;
# this only affects display in this terminal.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

load_dotenv()
from agents.graph import build_graph
from models import AgentAction, GrievanceCategory, Ticket


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket_id", nargs="?", help="ticket UUID; omit and pass --random instead")
    parser.add_argument("--random", action="store_true", help="pick a random seeded ticket")
    args = parser.parse_args()
    if not args.ticket_id and not args.random:
        raise SystemExit("Pass a ticket_id or --random.")

    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        ticket = (
            session.scalar(select(Ticket).order_by(func.random()).limit(1))
            if args.random
            else session.get(Ticket, args.ticket_id)
        )
        if ticket is None:
            raise SystemExit("No matching ticket found.")

        print(f"Ticket {ticket.id}")
        print(f"Narrative: {ticket.narrative}")
        if ticket.seeded_category_id is not None:
            seeded_category = session.get(GrievanceCategory, ticket.seeded_category_id)
            print(f"Seeded (ground-truth) category: {seeded_category.category_name}")
        else:
            print("Seeded (ground-truth) category: none -- real customer-submitted ticket")
        print(f"Current priority: {ticket.priority.value}\n")

        graph = build_graph(session)
        final_state = graph.invoke({"ticket_id": str(ticket.id), "route": None, "agent_action_id": None})

        if final_state["agent_action_id"] is None:
            print(f"Router sent this ticket to '{final_state['route']}' -- no triage needed, nothing written.")
            return
        action = session.get(AgentAction, final_state["agent_action_id"])
        print(f"--- Router chose '{final_state['route']}'; proposal written to agent_actions (pending) ---")
        print(f"agent_action_id: {action.id}")
        print(f"confidence:      {action.confidence}")
        print(f"proposed_output: {action.proposed_output}")


if __name__ == "__main__":
    main()
