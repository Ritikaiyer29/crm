from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import get_current_user
from api.schemas import CategoryOut
from database import get_session
from models import AppUser, GrievanceCategory

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
def list_categories(
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> list[CategoryOut]:
    # Categories aren't org-scoped (schema.sql seeds them globally, shared
    # across orgs) -- no filter needed here, unlike tickets/agent_actions.
    categories = session.scalars(select(GrievanceCategory).order_by(GrievanceCategory.category_name)).all()
    return [CategoryOut(id=c.id, category_name=c.category_name) for c in categories]
