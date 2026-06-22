from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_assignment import TicketAssignment
from src.models.user import User
from src.schemas.ticket import (
    AssigneeSummary,
    BatchFsmStatusEntry,
    BatchFsmStatusResponse,
    FollowUpTicketCreate,
    TagDeltaRequest,
    TagDeltaResponse,
    TagResponse,
    TicketCreate,
    TicketFsmResponse,
    TicketResponse,
    TicketUpdate,
)
from src.services.event_service import emit_event


async def _resolve_tags(session: AsyncSession, tag_names: list[str]) -> list:
    from src.models.tag import Tag

    result = []
    seen: set[str] = set()
    for raw_name in tag_names:
        name = raw_name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        existing = await session.execute(select(Tag).where(Tag.name == name))
        tag = existing.scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            await session.flush()
        result.append(tag)
    return result


async def _load_ticket_response(session: AsyncSession, ticket: Ticket) -> TicketResponse:
    stmt = (
        select(Ticket)
        .where(Ticket.id == ticket.id)
        .options(
            selectinload(Ticket.creator),
            selectinload(Ticket.assignments).selectinload(TicketAssignment.user),
            selectinload(Ticket.progress_updates),
            selectinload(Ticket.tags),
            selectinload(Ticket.project),
        )
    )
    result = await session.execute(stmt)
    t = result.scalar_one()

    progress_user_ids = {pu.user_id for pu in t.progress_updates}
    assignees = [
        AssigneeSummary(
            user_id=a.user_id,
            email=a.user.email,
            has_progress_update=a.user_id in progress_user_ids,
        )
        for a in t.assignments
    ]

    follow_up_count_result = await session.execute(
        select(func.count()).where(
            Ticket.parent_ticket_id == ticket.id,
            Ticket.deleted_at.is_(None),
        )
    )
    follow_up_count = follow_up_count_result.scalar() or 0

    display_id: str | None = None
    if t.project and t.project.code and t.number is not None:
        display_id = f"{t.project.code}-{t.number:04d}"

    return TicketResponse(
        id=t.id,
        display_id=display_id,
        number=t.number,
        project_id=t.project_id,
        parent_ticket_id=t.parent_ticket_id,
        title=t.title,
        description=t.description,
        status=t.status,
        ticket_type=t.ticket_type,
        ticket_spec=t.ticket_spec,
        urgent=t.urgent,
        blocker=t.blocker,
        bugfix=t.bugfix,
        created_by=t.creator,
        created_at=t.created_at,
        updated_at=t.updated_at,
        assignees=assignees,
        follow_up_count=follow_up_count,
        tags=[TagResponse(id=tag.id, name=tag.name) for tag in t.tags],
    )


async def _next_ticket_number(session: AsyncSession, project_id: UUID) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(Ticket.number), 0) + 1).where(Ticket.project_id == project_id)
    )
    return result.scalar() or 1


async def create_ticket(
    session: AsyncSession,
    project_id: UUID,
    data: TicketCreate,
    actor: User,
) -> TicketResponse:
    from src.models.project import Project

    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    number = await _next_ticket_number(session, project_id)

    ticket = Ticket(
        project_id=project_id,
        title=data.title,
        description=data.description,
        created_by=actor.id,
        status=TicketStatus.OPEN,
        number=number,
        ticket_type=data.ticket_type,
        ticket_spec=data.ticket_spec,
        urgent=data.urgent,
        blocker=data.blocker,
        bugfix=data.bugfix,
    )
    session.add(ticket)
    await session.flush()

    if data.tags:
        ticket.tags = await _resolve_tags(session, data.tags)

    await emit_event(
        session,
        ticket.id,
        "ticket.created",
        actor,
        prev_state=None,
        new_state={
            "title": ticket.title,
            "status": ticket.status.value,
            "project_id": str(ticket.project_id),
        },
    )
    await session.commit()
    return await _load_ticket_response(session, ticket)


async def create_follow_up(
    session: AsyncSession,
    parent_ticket_id: UUID,
    data: FollowUpTicketCreate,
    actor: User,
) -> TicketResponse:
    parent = await session.get(Ticket, parent_ticket_id)
    if parent is None or parent.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent ticket not found")

    number = await _next_ticket_number(session, parent.project_id)

    ticket = Ticket(
        project_id=parent.project_id,
        parent_ticket_id=parent_ticket_id,
        title=data.title,
        description=data.description,
        created_by=actor.id,
        status=TicketStatus.OPEN,
        number=number,
        ticket_type=data.ticket_type,
        ticket_spec=data.ticket_spec,
        urgent=data.urgent,
        blocker=data.blocker,
        bugfix=data.bugfix,
    )
    session.add(ticket)
    await session.flush()

    if data.tags:
        ticket.tags = await _resolve_tags(session, data.tags)

    await emit_event(
        session,
        ticket.id,
        "ticket.created",
        actor,
        prev_state=None,
        new_state={
            "title": ticket.title,
            "status": ticket.status.value,
            "project_id": str(ticket.project_id),
        },
    )
    await session.commit()
    return await _load_ticket_response(session, ticket)


async def update_ticket(
    session: AsyncSession,
    ticket_id: UUID,
    data: TicketUpdate,
    actor: User,
) -> TicketResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if ticket.created_by != actor.id and actor.role.value != "administrator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the ticket creator")

    prev_state = {"title": ticket.title, "description": ticket.description}
    if data.title is not None:
        ticket.title = data.title
    if data.description is not None:
        ticket.description = data.description
    if data.ticket_type is not None:
        ticket.ticket_type = data.ticket_type
    if data.ticket_spec is not None:
        ticket.ticket_spec = data.ticket_spec
    if data.urgent is not None:
        ticket.urgent = data.urgent
    if data.blocker is not None:
        ticket.blocker = data.blocker
    if data.bugfix is not None:
        ticket.bugfix = data.bugfix

    await emit_event(
        session,
        ticket.id,
        "ticket.updated",
        actor,
        prev_state=prev_state,
        new_state={"title": ticket.title, "description": ticket.description},
    )
    await session.commit()
    return await _load_ticket_response(session, ticket)


async def delete_ticket(
    session: AsyncSession,
    ticket_id: UUID,
    actor: User,
) -> None:
    from datetime import UTC, datetime

    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if ticket.created_by != actor.id and actor.role.value != "administrator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the ticket creator")

    follow_up_count_result = await session.execute(
        select(func.count()).where(
            Ticket.parent_ticket_id == ticket_id,
            Ticket.deleted_at.is_(None),
        )
    )
    if (follow_up_count_result.scalar() or 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete ticket with active follow-up tickets",
        )

    prev_state = {"title": ticket.title, "status": ticket.status.value}
    ticket.deleted_at = datetime.now(UTC)

    await emit_event(
        session,
        ticket.id,
        "ticket.deleted",
        actor,
        prev_state=prev_state,
        new_state=None,
    )
    await session.commit()


async def get_ticket(session: AsyncSession, ticket_id: UUID) -> TicketResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return await _load_ticket_response(session, ticket)


async def list_tickets(
    session: AsyncSession,
    project_id: UUID,
    status_filter: TicketStatus | None = None,
    assignee_id: UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[TicketResponse], int]:
    from src.models.project import Project

    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    base_stmt = select(Ticket).where(
        Ticket.project_id == project_id,
        Ticket.deleted_at.is_(None),
    )
    if status_filter is not None:
        base_stmt = base_stmt.where(Ticket.status == status_filter)
    if assignee_id is not None:
        base_stmt = base_stmt.where(
            Ticket.id.in_(
                select(TicketAssignment.ticket_id).where(TicketAssignment.user_id == assignee_id)
            )
        )

    count_result = await session.execute(select(func.count()).select_from(base_stmt.subquery()))
    total = count_result.scalar() or 0

    paginated = (
        base_stmt.order_by(Ticket.number.asc().nulls_last())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    tickets_result = await session.execute(paginated)
    tickets = tickets_result.scalars().all()

    responses = [await _load_ticket_response(session, t) for t in tickets]
    return responses, total


async def add_tag(
    session: AsyncSession,
    ticket_id: UUID,
    tag_name: str,
    actor: User,
) -> TicketResponse:
    from src.models.tag import Tag

    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    await session.refresh(ticket, ["tags"])
    if len(ticket.tags) >= 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum 10 tags per ticket"
        )

    existing = await session.execute(select(Tag).where(Tag.name == tag_name.strip()))
    tag = existing.scalar_one_or_none()
    if tag is None:
        tag = Tag(name=tag_name.strip())
        session.add(tag)
        await session.flush()

    if tag not in ticket.tags:
        ticket.tags.append(tag)
        await session.commit()

    return await _load_ticket_response(session, ticket)


async def remove_tag(
    session: AsyncSession,
    ticket_id: UUID,
    tag_name: str,
    actor: User,
) -> TicketResponse:
    from src.models.tag import Tag

    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    await session.refresh(ticket, ["tags"])
    existing = await session.execute(select(Tag).where(Tag.name == tag_name))
    tag = existing.scalar_one_or_none()
    if tag and tag in ticket.tags:
        ticket.tags.remove(tag)
        await session.commit()

    return await _load_ticket_response(session, ticket)


async def apply_tag_delta(
    session: AsyncSession,
    project_id: UUID,
    ticket_id: UUID,
    body: TagDeltaRequest,
    actor: User,
) -> TagDeltaResponse:
    from src.models.project import Project
    from src.models.tag import Tag
    from src.models.user import UserRole

    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if ticket.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    # Require project ownership or admin to modify tags
    if getattr(actor, "role", None) != UserRole.administrator:
        project = await session.get(Project, project_id)
        if project is None or project.created_by != getattr(actor, "id", None):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    await session.refresh(ticket, ["tags"])

    if body.remove:
        remove_names = {n.strip() for n in body.remove if n.strip()}
        ticket.tags = [t for t in ticket.tags if t.name not in remove_names]

    if body.add:
        existing_names = {t.name for t in ticket.tags}
        for raw_name in body.add:
            name = raw_name.strip()
            if not name or name in existing_names:
                continue
            existing_names.add(name)
            tag_result = await session.execute(select(Tag).where(Tag.name == name))
            tag = tag_result.scalar_one_or_none()
            if tag is None:
                tag = Tag(name=name)
                session.add(tag)
                await session.flush()
            ticket.tags.append(tag)

    if len(ticket.tags) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum 10 tags per ticket"
        )

    await session.commit()
    await session.refresh(ticket, ["tags"])
    return TagDeltaResponse(tags=[t.name for t in ticket.tags])


async def batch_fsm_status(
    session: AsyncSession,
    ticket_ids: list[UUID],
    caller: object,
) -> BatchFsmStatusResponse:
    from src.models.project import Project
    from src.models.user import UserRole

    if not ticket_ids:
        return BatchFsmStatusResponse(statuses={})

    stmt = select(Ticket).where(
        Ticket.id.in_(ticket_ids),
        Ticket.deleted_at.is_(None),
    )

    # Non-admins can only see tickets in projects they created
    if getattr(caller, "role", None) != UserRole.administrator:
        caller_projects = await session.execute(
            select(Project.id).where(Project.created_by == getattr(caller, "id", None))
        )
        accessible_project_ids = [row[0] for row in caller_projects.all()]
        stmt = stmt.where(Ticket.project_id.in_(accessible_project_ids))

    result = await session.execute(stmt)
    tickets = result.scalars().all()

    statuses = {
        str(t.id): BatchFsmStatusEntry(
            fsm_status=t.fsm_status,
            title=t.title,
            blocked_reason=t.blocked_reason,
        )
        for t in tickets
    }
    return BatchFsmStatusResponse(statuses=statuses)


async def list_tickets_with_fsm(
    session: AsyncSession,
    project_id: UUID,
    status_filter: TicketStatus | None = None,
    assignee_id: UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[TicketFsmResponse], int]:
    from src.models.project import Project
    from src.services.fsm_service import _load_fsm_response

    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    base_stmt = select(Ticket).where(
        Ticket.project_id == project_id,
        Ticket.deleted_at.is_(None),
    )
    if status_filter is not None:
        base_stmt = base_stmt.where(Ticket.status == status_filter)
    if assignee_id is not None:
        base_stmt = base_stmt.where(
            Ticket.id.in_(
                select(TicketAssignment.ticket_id).where(TicketAssignment.user_id == assignee_id)
            )
        )

    count_result = await session.execute(select(func.count()).select_from(base_stmt.subquery()))
    total = count_result.scalar() or 0

    paginated = (
        base_stmt.order_by(Ticket.number.asc().nulls_last())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    tickets_result = await session.execute(paginated)
    tickets = tickets_result.scalars().all()

    responses = [await _load_fsm_response(session, t) for t in tickets]
    return responses, total
