from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.ticket import FsmStatus, Ticket
from src.models.ticket_assignment import TicketAssignment
from src.schemas.orchestrator import (
    PendingTicketsResponse,
    TicketPendingSummary,
    decode_cursor,
    encode_cursor,
)
from src.schemas.ticket import FsmPatchRequest, OverrideRequest, TicketFsmResponse

log = structlog.get_logger(__name__)


async def _load_fsm_response(session: AsyncSession, ticket: Ticket) -> TicketFsmResponse:
    from src.schemas.ticket import AssigneeSummary, TagResponse

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

    display_id = None
    if t.project and t.project.code and t.number is not None:
        display_id = f"{t.project.code}-{t.number:04d}"

    return TicketFsmResponse(
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
        fsm_status=t.fsm_status,
        blocked_reason=t.blocked_reason,
        brainstorm_round=t.brainstorm_round,
        assigned_agent=t.assigned_agent,
        override=t.override,
        override_reason=t.override_reason,
        last_orchestrator_run=t.last_orchestrator_run,
        orchestrator_errors=t.orchestrator_errors,
    )


async def get_pending_tickets(
    session: AsyncSession,
    project_id: UUID | None,
    limit: int,
    after_cursor: str | None,
) -> PendingTicketsResponse:
    base_filter = [
        Ticket.deleted_at.is_(None),
        Ticket.fsm_status.is_distinct_from(FsmStatus.done),
        or_(
            Ticket.last_orchestrator_run.is_(None),
            Ticket.updated_at > Ticket.last_orchestrator_run,
        ),
    ]
    if project_id is not None:
        base_filter.append(Ticket.project_id == project_id)

    count_stmt = select(func.count()).where(*base_filter)
    total_pending = (await session.execute(count_stmt)).scalar() or 0

    stmt = select(Ticket).where(*base_filter).order_by(Ticket.updated_at.asc(), Ticket.id.asc())

    if after_cursor:
        try:
            cursor_updated_at, cursor_id = decode_cursor(after_cursor)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor")
        stmt = stmt.where(
            or_(
                Ticket.updated_at > cursor_updated_at,
                and_(
                    Ticket.updated_at == cursor_updated_at,
                    Ticket.id > cursor_id,
                ),
            )
        )

    stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    tickets = result.scalars().all()

    items = []
    for t in tickets:
        follow_up_ids_result = await session.execute(
            select(Ticket.id).where(
                Ticket.parent_ticket_id == t.id,
                Ticket.deleted_at.is_(None),
            )
        )
        follow_up_ids = [row[0] for row in follow_up_ids_result.all()]

        items.append(
            TicketPendingSummary(
                id=t.id,
                project_id=t.project_id,
                title=t.title,
                status=t.status.value,
                fsm_status=t.fsm_status,
                blocked_reason=t.blocked_reason,
                brainstorm_round=t.brainstorm_round,
                assigned_agent=t.assigned_agent,
                override=t.override,
                last_orchestrator_run=t.last_orchestrator_run,
                created_at=t.created_at,
                updated_at=t.updated_at,
                follow_up_ids=follow_up_ids,
            )
        )

    next_cursor = None
    if len(tickets) == limit and tickets:
        last = tickets[-1]
        next_cursor = encode_cursor(last.updated_at, last.id)

    return PendingTicketsResponse(
        tickets=items,
        total_pending=total_pending,
        next_cursor=next_cursor,
    )


async def patch_fsm_fields(
    session: AsyncSession,
    project_id: UUID,
    ticket_id: UUID,
    body: FsmPatchRequest,
    current_user: object,
) -> TicketFsmResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if ticket.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    prev_fsm_status = ticket.fsm_status

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ticket, field, value)

    if ticket.orchestrator_errors and len(ticket.orchestrator_errors) > 50:
        ticket.orchestrator_errors = ticket.orchestrator_errors[-50:]

    ticket.updated_at = datetime.now(UTC)
    await session.commit()

    log.info(
        "fsm.patch",
        ticket_id=str(ticket_id),
        from_state=prev_fsm_status.value if prev_fsm_status else None,
        to_state=ticket.fsm_status.value if ticket.fsm_status else None,
    )

    return await _load_fsm_response(session, ticket)


async def set_override(
    session: AsyncSession,
    project_id: UUID,
    ticket_id: UUID,
    body: OverrideRequest,
    current_user: object,
) -> TicketFsmResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if ticket.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    ticket.override = body.override
    ticket.override_reason = body.override_reason
    await session.commit()

    log.info(
        "fsm.override",
        ticket_id=str(ticket_id),
        override=body.override,
    )

    return await _load_fsm_response(session, ticket)


async def get_ticket_full(
    session: AsyncSession,
    project_id: UUID,
    ticket_id: UUID,
) -> TicketFsmResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    if ticket.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    return await _load_fsm_response(session, ticket)
