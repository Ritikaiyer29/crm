"""
Shared graph state. LangGraph nodes are stateless functions -- everything a
node needs to do its job has to be explicit here, not implied by prior
conversation turns. That's deliberate: it keeps every node independently
testable and every decision traceable back to what was actually in state
when the agent ran (rather than some hidden memory buffer).
"""
from __future__ import annotations

from typing import Optional, TypedDict


class GraphState(TypedDict):
    ticket_id: str
    route: Optional[str]           # set by the router; read by the conditional edge
    agent_action_id: Optional[str]  # the pending agent_actions row this run produced
