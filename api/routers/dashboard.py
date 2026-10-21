from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.auth import get_current_user
from api.schemas import (
    AgentStats,
    CategoryCount,
    DashboardStats,
    DeadlineItem,
    RecentActivityItem,
    TicketStats,
    WeeklyCount,
)
from database import get_session
from models import AgentAction, ApprovalStatus, AppUser, Contact, GrievanceCategory, Ticket, TicketStatus

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_WEEKS = 26
_TOP_CATEGORIES = 8


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    session: Session = Depends(get_session),
    current_user: AppUser = Depends(get_current_user),
) -> DashboardStats:
    org_id = current_user.org_id
    now = datetime.now(timezone.utc)
    unresolved = Ticket.status != TicketStatus.resolved

    by_status = dict(
        session.execute(
            select(Ticket.status, func.count()).where(Ticket.org_id == org_id).group_by(Ticket.status)
        ).all()
    )
    by_priority = dict(
        session.execute(
            select(Ticket.priority, func.count()).where(Ticket.org_id == org_id).group_by(Ticket.priority)
        ).all()
    )
    overdue, due_7d, resolved_on_time, resolved_with_dates = session.execute(
        select(
            func.count().filter(unresolved, Ticket.regulatory_deadline < now),
            func.count().filter(
                unresolved, Ticket.regulatory_deadline >= now, Ticket.regulatory_deadline < now + timedelta(days=7)
            ),
            func.count().filter(
                Ticket.resolved_at.isnot(None), Ticket.resolved_at <= Ticket.regulatory_deadline
            ),
            func.count().filter(Ticket.resolved_at.isnot(None), Ticket.regulatory_deadline.isnot(None)),
        ).where(Ticket.org_id == org_id)
    ).one()

    total = sum(by_status.values())
    resolved = by_status.get(TicketStatus.resolved, 0)
    tickets = TicketStats(
        total=total,
        open=total - resolved,
        resolved=resolved,
        overdue=overdue,
        due_7d=due_7d,
        on_time_rate=(resolved_on_time / resolved_with_dates) if resolved_with_dates else None,
        by_status={s.value: by_status.get(s, 0) for s in TicketStatus},
        by_priority={p.value: c for p, c in by_priority.items()},
    )

    this_week = (now - timedelta(days=now.weekday())).date()
    first_week = this_week - timedelta(weeks=_WEEKS - 1)
    week_col = func.date_trunc("week", Ticket.date_received)
    week_counts = {
        w.date(): c
        for w, c in session.execute(
            select(week_col, func.count())
            .where(Ticket.org_id == org_id, Ticket.date_received >= first_week)
            .group_by(week_col)
        ).all()
    }
    weekly = [
        WeeklyCount(week_start=first_week + timedelta(weeks=i), count=week_counts.get(first_week + timedelta(weeks=i), 0))
        for i in range(_WEEKS)
    ]

    category_rows = session.execute(
        select(GrievanceCategory.id, GrievanceCategory.category_name, func.count())
        .join(Ticket, Ticket.category_id == GrievanceCategory.id)
        .where(Ticket.org_id == org_id)
        .group_by(GrievanceCategory.id, GrievanceCategory.category_name)
        .order_by(func.count().desc())
    ).all()
    top = [CategoryCount(id=i, category_name=n, count=c) for i, n, c in category_rows[:_TOP_CATEGORIES]]

    def status_count(s: ApprovalStatus):
        return func.count().filter(AgentAction.approval_status == s)

    agent_rows = session.execute(
        select(
            AgentAction.agent_name,
            status_count(ApprovalStatus.pending),
            status_count(ApprovalStatus.approved),
            status_count(ApprovalStatus.edited),
            status_count(ApprovalStatus.rejected),
            func.avg(AgentAction.confidence),
        )
        .where(AgentAction.org_id == org_id)
        .group_by(AgentAction.agent_name)
        .order_by(AgentAction.agent_name)
    ).all()
    agents = [
        AgentStats(
            agent_name=name, pending=p, approved=a, edited=e, rejected=r,
            avg_confidence=float(conf) if conf is not None else None,
        )
        for name, p, a, e, r, conf in agent_rows
    ]

    deadline_rows = session.execute(
        select(Ticket, Contact.full_name, GrievanceCategory.category_name)
        .join(Contact, Contact.id == Ticket.contact_id)
        .join(GrievanceCategory, GrievanceCategory.id == Ticket.category_id)
        .where(Ticket.org_id == org_id, unresolved, Ticket.regulatory_deadline >= now)
        .order_by(Ticket.regulatory_deadline)
        .limit(6)
    ).all()
    upcoming = [
        DeadlineItem(
            id=t.id, contact_name=name, category_name=cat, priority=t.priority.value,
            status=t.status.value, regulatory_deadline=t.regulatory_deadline,
        )
        for t, name, cat in deadline_rows
    ]

    activity_rows = session.execute(
        select(AgentAction, Contact.full_name)
        .outerjoin(Ticket, Ticket.id == AgentAction.ticket_id)
        .outerjoin(Contact, Contact.id == Ticket.contact_id)
        .where(AgentAction.org_id == org_id)
        .order_by(func.coalesce(AgentAction.resolved_at, AgentAction.created_at).desc())
        .limit(8)
    ).all()
    activity = [
        RecentActivityItem(
            id=a.id, agent_name=a.agent_name, action_type=a.action_type,
            approval_status=a.approval_status.value, created_at=a.created_at, resolved_at=a.resolved_at,
            ticket_id=a.ticket_id, contact_name=name,
        )
        for a, name in activity_rows
    ]

    return DashboardStats(
        tickets=tickets,
        weekly_volume=weekly,
        top_categories=top,
        agents=agents,
        pending_approvals=sum(a.pending for a in agents),
        upcoming_deadlines=upcoming,
        recent_activity=activity,
    )
