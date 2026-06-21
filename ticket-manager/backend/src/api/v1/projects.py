import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.project import Project
from src.models.ticket import Ticket, TicketStatus
from src.models.user import User
from src.schemas.project import ProjectCreate, ProjectResponse, ProjectTicketCounts
from src.schemas.ticket import (
    TicketCreate,
    TicketFsmListResponse,
    TicketListResponse,
    TicketResponse,
)
from src.services import ticket_service

router = APIRouter(tags=["Projects"])

_OPEN_STATUSES = {TicketStatus.OPEN}
_ACTIVE_STATUSES = {TicketStatus.IN_PROGRESS, TicketStatus.IN_REVIEW}
_DONE_STATUSES = {TicketStatus.DONE, TicketStatus.CLOSED}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")


async def _ticket_counts(db: AsyncSession, project_id: UUID) -> ProjectTicketCounts:
    rows = await db.execute(
        select(Ticket.status, func.count())
        .where(Ticket.project_id == project_id)
        .group_by(Ticket.status)
    )
    counts: dict[TicketStatus, int] = {row[0]: row[1] for row in rows}
    return ProjectTicketCounts(
        open=sum(counts.get(s, 0) for s in _OPEN_STATUSES),
        active=sum(counts.get(s, 0) for s in _ACTIVE_STATUSES),
        done=sum(counts.get(s, 0) for s in _DONE_STATUSES),
    )


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    existing_code = await db.execute(select(Project).where(Project.code == body.code))
    if existing_code.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Project code already in use.")

    slug_base = _slugify(body.name)
    slug = slug_base
    counter = 1
    while True:
        existing_slug = await db.execute(select(Project).where(Project.slug == slug))
        if not existing_slug.scalar_one_or_none():
            break
        slug = f"{slug_base}-{counter}"
        counter += 1

    project = Project(name=body.name, slug=slug, code=body.code, created_by=current_user.id)
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        code=project.code,
        created_at=project.created_at,
        ticket_counts=ProjectTicketCounts(open=0, active=0, done=0),
    )


@router.get("/projects", status_code=200)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()

    items = []
    for p in projects:
        counts = await _ticket_counts(db, p.id)
        items.append(
            ProjectResponse(
                id=p.id,
                name=p.name,
                slug=p.slug,
                code=p.code,
                created_at=p.created_at,
                ticket_counts=counts,
            ).model_dump(mode="json")
        )
    return {"items": items}


@router.get("/projects/{project_id}/tickets")
async def list_tickets(
    project_id: UUID,
    status: TicketStatus | None = Query(default=None),
    assignee_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    include_fsm: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> TicketListResponse | TicketFsmListResponse:
    if include_fsm:
        fsm_items, total = await ticket_service.list_tickets_with_fsm(
            db, project_id, status, assignee_id, page, page_size
        )
        return TicketFsmListResponse(tickets=fsm_items, total=total)
    plain_items, total = await ticket_service.list_tickets(
        db, project_id, status, assignee_id, page, page_size
    )
    return TicketListResponse(tickets=plain_items, total=total)


@router.post("/projects/{project_id}/tickets", response_model=TicketResponse, status_code=201)
async def create_ticket(
    project_id: UUID,
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TicketResponse:
    return await ticket_service.create_ticket(db, project_id, body, current_user)
