"""Customer-facing endpoints -- no login required.

Everything else in api/routers/ is the internal ops surface, scoped to the
authenticated user's org. This router is the other side of that: how a
ticket enters the system in the first place, from someone who isn't staff
and has no account.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import ComplaintStatusOut, ComplaintSubmitOut, ComplaintSubmitRequest
from database import get_session
from models import Contact, GrievanceCategory, Org, Ticket

router = APIRouter(prefix="/complaints", tags=["public"])

# The NCH taxonomy's real catch-all category (see seed_data.py) -- the
# correct starting category_id for a ticket nobody has triaged yet.
_UNTRIAGED_CATEGORY_NAME = "Other"


def _get_demo_org(session: Session) -> Org:
    # Single-tenant demo: exactly one org exists (see create_admin_user.py).
    # A multi-bank version of this would need the submitter to say which
    # bank they're complaining about; out of scope here.
    org = session.scalars(select(Org)).first()
    if org is None:
        raise HTTPException(status_code=503, detail="No organization configured yet")
    return org


@router.post("", response_model=ComplaintSubmitOut, status_code=201)
def submit_complaint(
    payload: ComplaintSubmitRequest,
    session: Session = Depends(get_session),
) -> ComplaintSubmitOut:
    org = _get_demo_org(session)
    category = session.scalar(
        select(GrievanceCategory).where(GrievanceCategory.category_name == _UNTRIAGED_CATEGORY_NAME)
    )
    if category is None:
        raise HTTPException(status_code=503, detail="Category taxonomy not seeded yet")

    contact = Contact(org_id=org.id, full_name=payload.full_name, email=payload.email, phone=payload.phone)
    session.add(contact)
    session.flush()  # need contact.id before the ticket row references it

    ticket = Ticket(
        org_id=org.id,
        contact_id=contact.id,
        category_id=category.id,
        seeded_category_id=None,  # real complaint -- no eval ground truth
        company=org.name,
        narrative=payload.narrative,
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    return ComplaintSubmitOut(id=ticket.id, status=ticket.status.value, regulatory_deadline=ticket.regulatory_deadline)


@router.get("/{ticket_id}", response_model=ComplaintStatusOut)
def check_complaint_status(
    ticket_id: str,
    session: Session = Depends(get_session),
) -> ComplaintStatusOut:
    # The ticket's UUID doubles as the customer's reference number -- it's
    # unguessable (128 bits of randomness), so "know the ID" is an
    # acceptable bar for a status lookup with no login, the same way a
    # courier tracking number works.
    try:
        ticket = session.get(Ticket, ticket_id)
    except Exception:
        ticket = None
    if ticket is None:
        raise HTTPException(status_code=404, detail="No complaint found with that reference")

    category = session.get(GrievanceCategory, ticket.category_id)
    return ComplaintStatusOut(
        id=ticket.id,
        status=ticket.status.value,
        category_name=category.category_name,
        priority=ticket.priority.value,
        date_received=ticket.date_received,
        regulatory_deadline=ticket.regulatory_deadline,
        resolved_at=ticket.resolved_at,
    )
