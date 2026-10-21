from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api.auth import get_current_user
from api.routers.agent_actions import action_out
from api.schemas import TicketDetailOut, TicketOut
from database import get_session
from models import AgentAction, AppUser, Contact, GrievanceCategory, Ticket, TicketPriority, TicketStatus

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _ticket_out(session: Session, ticket: Ticket) -> TicketOut:
    category = session.get(GrievanceCategory, ticket.category_id)
    contact = session.get(Contact, ticket.contact_id)
    return TicketOut(
        id=ticket.id,
        narrative=ticket.narrative,
        category_name=category.category_name,
        status=ticket.status.value,
        priority=ticket.priority.value,
        date_received=ticket.date_received,
        regulatory_deadline=ticket.regulatory_deadline,
        contact_name=contact.full_name,
    )


@router.get("", response_model=list[TicketOut])
def list_tickets(
    status_filter: Optional[str] = Query(None, alias="status"),
    priority: Optional[str] = None,
    category_id: Optional[uuid.UUID] = None,
    q: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> list[TicketOut]:
    # App-level org scoping, not Postgres row-level security -- the original
    # architecture notes mentioned RLS as the reason for picking Supabase,
    # but that assumes PostgREST setting session GUCs from JWT claims. We
    # connect via plain SQLAlchemy/psycopg2, so RLS policies would never see
    # those claims; filtering by org_id here is the correct equivalent for
    # that connection path. Worth real RLS policies if this ever gets a
    # second org and a Postgres-level connection pool shared across tenants.
    query = select(Ticket).where(Ticket.org_id == current_user.org_id)
    if status_filter:
        try:
            query = query.where(Ticket.status == TicketStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {status_filter!r}")
    if priority:
        try:
            query = query.where(Ticket.priority == TicketPriority(priority))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid priority: {priority!r}")
    if category_id:
        query = query.where(Ticket.category_id == category_id)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.join(Contact, Contact.id == Ticket.contact_id).where(
            or_(Ticket.narrative.ilike(pattern), Contact.full_name.ilike(pattern))
        )
    query = query.order_by(Ticket.date_received.desc()).offset(offset).limit(limit)
    tickets = session.scalars(query).all()
    return [_ticket_out(session, t) for t in tickets]


@router.get("/{ticket_id}", response_model=TicketDetailOut)
def get_ticket(
    ticket_id: str,
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> TicketDetailOut:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None or ticket.org_id != current_user.org_id:
        raise HTTPException(status_code=404, detail="Ticket not found")

    base = _ticket_out(session, ticket)
    actions = session.scalars(
        select(AgentAction).where(AgentAction.ticket_id == ticket.id).order_by(AgentAction.created_at.desc())
    ).all()
    return TicketDetailOut(**base.model_dump(), agent_actions=[action_out(session, a) for a in actions])
