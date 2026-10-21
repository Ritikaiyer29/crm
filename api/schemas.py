"""Pydantic request/response models for the FastAPI app."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TicketOut(BaseModel):
    id: uuid.UUID
    narrative: str
    category_name: str
    status: str
    priority: str
    date_received: datetime
    regulatory_deadline: Optional[datetime]
    contact_name: str


class AgentActionOut(BaseModel):
    id: uuid.UUID
    agent_name: str
    action_type: str
    input_summary: Optional[str]
    proposed_output: Optional[str]
    final_output: Optional[str]
    confidence: Optional[Decimal]
    approval_status: str
    created_at: datetime
    ticket_id: Optional[uuid.UUID]
    deal_id: Optional[uuid.UUID]
    # Denormalized context so the frontend's approval queue doesn't need a
    # second request per row just to show what the proposal is about.
    ticket_narrative: Optional[str] = None
    contact_name: Optional[str] = None
    # Only set for agent_name="triage" -- pulled out of tool_calls so the
    # frontend can prefill an edit form without parsing proposed_output's
    # human-readable prose or needing raw tool_calls exposed.
    proposed_category_id: Optional[uuid.UUID] = None
    proposed_priority: Optional[str] = None


class CategoryOut(BaseModel):
    id: uuid.UUID
    category_name: str


class TicketDetailOut(TicketOut):
    agent_actions: list[AgentActionOut]


class EditActionRequest(BaseModel):
    # triage edits use category_id + priority; follow_up/sales_copilot edits use text.
    category_id: Optional[uuid.UUID] = None
    priority: Optional[str] = None
    text: Optional[str] = None


class ComplaintSubmitRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = None
    narrative: str = Field(min_length=20, max_length=5000)


class ComplaintSubmitOut(BaseModel):
    id: uuid.UUID
    status: str
    regulatory_deadline: Optional[datetime]


class TicketStats(BaseModel):
    total: int
    open: int
    resolved: int
    overdue: int
    due_7d: int
    on_time_rate: Optional[float]
    by_status: dict[str, int]
    by_priority: dict[str, int]


class WeeklyCount(BaseModel):
    week_start: date
    count: int


class CategoryCount(BaseModel):
    id: uuid.UUID
    category_name: str
    count: int


class AgentStats(BaseModel):
    agent_name: str
    pending: int
    approved: int
    edited: int
    rejected: int
    avg_confidence: Optional[float]


class DeadlineItem(BaseModel):
    id: uuid.UUID
    contact_name: str
    category_name: str
    priority: str
    status: str
    regulatory_deadline: datetime


class RecentActivityItem(BaseModel):
    id: uuid.UUID
    agent_name: str
    action_type: str
    approval_status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    ticket_id: Optional[uuid.UUID]
    contact_name: Optional[str]


class DashboardStats(BaseModel):
    tickets: TicketStats
    weekly_volume: list[WeeklyCount]
    top_categories: list[CategoryCount]
    agents: list[AgentStats]
    pending_approvals: int
    upcoming_deadlines: list[DeadlineItem]
    recent_activity: list[RecentActivityItem]


class ComplaintStatusOut(BaseModel):
    id: uuid.UUID
    status: str
    category_name: str
    priority: str
    date_received: datetime
    regulatory_deadline: Optional[datetime]
    resolved_at: Optional[datetime]
