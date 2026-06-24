from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import UserClaims
from src.models.ticket import Ticket, TicketStatus
from src.models.ticket_assignment import TicketAssignment
from src.schemas.ticket import TicketResponse
from src.services.event_service import emit_event
from src.services.ticket_service import _load_ticket_response
from src.services.workflow_service import validate_transition


async def transition_ticket(
    session: AsyncSession,
    ticket_id: UUID,
    to_status: TicketStatus,
    actor: UserClaims,
) -> TicketResponse:
    ticket_result = await session.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.deleted_at.is_(None)).with_for_update()
    )
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    # Lock assignments for consistent RBAC snapshot
    all_assignments_result = await session.execute(
        select(TicketAssignment).where(TicketAssignment.ticket_id == ticket_id).with_for_update()
    )
    all_assignments = all_assignments_result.scalars().all()

    assignee_ids = {a.user_id for a in all_assignments}
    if actor.sub not in assignee_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only assignees may transition this ticket",
        )

    validate_transition(ticket.status, to_status)

    prev_status = ticket.status
    ticket.status = to_status

    await emit_event(
        session,
        ticket_id,
        "ticket.status_changed",
        actor,
        prev_state={"status": prev_status.value},
        new_state={"status": to_status.value},
    )
    await session.commit()
    return await _load_ticket_response(session, ticket)
