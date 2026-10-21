"""
LangGraph orchestrator: router -> specialist agent(s).

The router is ticket-keyed and decides, from the ticket's current state,
which lifecycle stage it's in:
  - never triaged                                          -> triage_agent
  - triaged, and within AT_RISK_THRESHOLD_DAYS of its
    regulatory_deadline (or already past it)                -> follow_up_agent
  - anything else                                           -> nothing to do (END)

This same graph is meant to be invoked two ways: once per ticket right after
it's created (an eventual FastAPI webhook), and in a periodic sweep across
many tickets (run_followup_sweep.py today; APScheduler/Celery later per the
original architecture plan). The router's job is identical either way:
"what does this ticket need right now."

The sales copilot agent is deliberately NOT a branch of this graph -- it
operates on a contact's deal history, not a single ticket's lifecycle, so
forcing it into this ticket-keyed state would mean stretching one state
shape to cover two different entities for no real benefit. See
agents/sales_copilot_agent.py for why it has its own entry point instead.
"""
from __future__ import annotations

from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.follow_up_agent import AT_RISK_THRESHOLD_DAYS, check_and_propose_followup
from agents.state import GraphState
from agents.triage_agent import run_triage
from models import AgentAction, Ticket, TicketStatus


def build_graph(session: Session):
    """Takes a live DB session so nodes can read/write real rows. Passed in
    rather than opened per-node so a whole graph run shares one transaction --
    important now that the router itself also needs to read the ticket."""

    def router(state: GraphState) -> GraphState:
        ticket = session.get(Ticket, state["ticket_id"])

        has_triage = (
            session.scalar(
                select(AgentAction).where(
                    AgentAction.ticket_id == ticket.id,
                    AgentAction.agent_name == "triage",
                )
            )
            is not None
        )
        if not has_triage:
            return {**state, "route": "triage"}

        if ticket.status != TicketStatus.resolved and ticket.regulatory_deadline is not None:
            days_remaining = (ticket.regulatory_deadline - datetime.now(timezone.utc)).days
            if days_remaining <= AT_RISK_THRESHOLD_DAYS:
                return {**state, "route": "follow_up"}

        return {**state, "route": "done"}

    def route_decision(state: GraphState) -> str:
        return state["route"]

    def triage_node(state: GraphState) -> GraphState:
        action = run_triage(session, state["ticket_id"])
        return {**state, "agent_action_id": str(action.id)}

    def follow_up_node(state: GraphState) -> GraphState:
        action = check_and_propose_followup(session, state["ticket_id"])
        return {**state, "agent_action_id": str(action.id) if action else None}

    graph = StateGraph(GraphState)
    graph.add_node("router", router)
    graph.add_node("triage_agent", triage_node)
    graph.add_node("follow_up_agent", follow_up_node)
    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_decision,
        {"triage": "triage_agent", "follow_up": "follow_up_agent", "done": END},
    )
    graph.add_edge("triage_agent", END)
    graph.add_edge("follow_up_agent", END)
    return graph.compile()
