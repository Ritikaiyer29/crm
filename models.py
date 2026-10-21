"""
SQLAlchemy 2.0 models for the agentic CRM.

These map 1:1 onto schema.sql. Run schema.sql against your Supabase
project first (SQL editor) — these models don't create tables, they
just give the FastAPI app and the agents typed access to them.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    ForeignKey, String, Text, Numeric, Integer, Boolean, Date, DateTime,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())


# ---------- Enums (mirror the Postgres types in schema.sql) ----------

class AccountProduct(str, enum.Enum):
    savings_account = "savings_account"
    current_account = "current_account"
    credit_card = "credit_card"
    upi_wallet = "upi_wallet"
    personal_loan = "personal_loan"
    nbfc_loan = "nbfc_loan"
    fixed_deposit = "fixed_deposit"


class AccountStatus(str, enum.Enum):
    active = "active"
    closed = "closed"
    dormant = "dormant"


class TicketStatus(str, enum.Enum):
    open = "open"
    in_review = "in_review"
    pending_approval = "pending_approval"
    resolved = "resolved"
    escalated = "escalated"


class TicketPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DealType(str, enum.Enum):
    retention_risk = "retention_risk"
    cross_sell = "cross_sell"


class DealStage(str, enum.Enum):
    identified = "identified"
    in_progress = "in_progress"
    actioned = "actioned"
    closed = "closed"


class ActivityType(str, enum.Enum):
    call = "call"
    email = "email"
    note = "note"
    agent_action = "agent_action"
    status_change = "status_change"


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    edited = "edited"
    auto_approved = "auto_approved"


class UserRole(str, enum.Enum):
    admin = "admin"
    agent = "agent"
    reviewer = "reviewer"


# ---------- Core tables ----------

class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(ENUM(UserRole, name="user_role"), default=UserRole.agent)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    accounts: Mapped[list["Account"]] = relationship(back_populates="contact")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="contact")
    deals: Mapped[list["Deal"]] = relationship(back_populates="contact")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    product: Mapped[AccountProduct] = mapped_column(ENUM(AccountProduct, name="account_product"), nullable=False)
    status: Mapped[AccountStatus] = mapped_column(ENUM(AccountStatus, name="account_status"), default=AccountStatus.active)
    opened_at: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contact: Mapped["Contact"] = relationship(back_populates="accounts")


class GrievanceCategory(Base):
    __tablename__ = "grievance_categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    category_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    sector: Mapped[str] = mapped_column(Text, default="banking")
    source: Mapped[str] = mapped_column(Text, default="National Consumer Helpline")
    typical_share: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"))
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("grievance_categories.id"), nullable=False)
    # Immutable eval ground truth -- see schema.sql for why this is separate
    # from category_id (which the approval flow can overwrite). NULL for
    # real customer-submitted tickets (api/routers/public.py), which have no
    # known true category -- only synthetic seed data has ground truth.
    seeded_category_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("grievance_categories.id"))
    company: Mapped[str] = mapped_column(Text, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(ENUM(TicketStatus, name="ticket_status"), default=TicketStatus.open)
    priority: Mapped[TicketPriority] = mapped_column(ENUM(TicketPriority, name="ticket_priority"), default=TicketPriority.medium)
    date_received: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # set by the trg_set_regulatory_deadline trigger in schema.sql — don't set this from Python
    regulatory_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contact: Mapped["Contact"] = relationship(back_populates="tickets")
    # foreign_keys required now that two columns FK to grievance_categories --
    # SQLAlchemy can no longer infer which one this relationship means.
    category: Mapped["GrievanceCategory"] = relationship(foreign_keys=[category_id])


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[DealType] = mapped_column(ENUM(DealType, name="deal_type"), nullable=False)
    stage: Mapped[DealStage] = mapped_column(ENUM(DealStage, name="deal_stage"), default=DealStage.identified)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contact: Mapped["Contact"] = relationship(back_populates="deals")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"))
    ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"))
    deal_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"))
    type: Mapped[ActivityType] = mapped_column(ENUM(ActivityType, name="activity_type"), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentAction(Base):
    """The audit trail — every agent decision, and whether/how a human approved it."""
    __tablename__ = "agent_actions"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id", ondelete="CASCADE"))
    deal_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"))
    agent_name: Mapped[str] = mapped_column(Text, nullable=False)       # 'triage' | 'sales_copilot' | 'rag_answer' | 'follow_up'
    action_type: Mapped[str] = mapped_column(Text, nullable=False)      # 'classify' | 'draft_response' | 'escalate' | ...
    input_summary: Mapped[Optional[str]] = mapped_column(Text)
    proposed_output: Mapped[Optional[str]] = mapped_column(Text)
    final_output: Mapped[Optional[str]] = mapped_column(Text)
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSONB)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approval_status: Mapped[ApprovalStatus] = mapped_column(ENUM(ApprovalStatus, name="approval_status"), default=ApprovalStatus.pending)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("app_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)   # e.g. 'RBI RB-IOS 2026'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KBChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(384))
