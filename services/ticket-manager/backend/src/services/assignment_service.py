from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import UserClaims
from src.models.ticket import Ticket
from src.models.ticket_assignment import TicketAssignment
from src.schemas.assignment import AssignmentResponse
from src.services.event_service import emit_event


async def assign_user(
    session: AsyncSession,
    ticket_id: UUID,
    user_id: str,
    actor: UserClaims,
) -> AssignmentResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    existing = await session.execute(
        select(TicketAssignment).where(
            TicketAssignment.ticket_id == ticket_id,
            TicketAssignment.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already assigned")

    assignment = TicketAssignment(
        ticket_id=ticket_id,
        user_id=user_id,
        assigned_by=actor.sub,
    )
    session.add(assignment)
    await session.flush()

    await emit_event(
        session,
        ticket_id,
        "ticket.assigned",
        actor,
        prev_state=None,
        new_state={"user_id": user_id},
    )
    await session.commit()
    await session.refresh(assignment)
    return AssignmentResponse.model_validate(assignment)


async def unassign_user(
    session: AsyncSession,
    ticket_id: UUID,
    user_id: str,
    actor: UserClaims,
) -> None:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if actor.sub != ticket.created_by and not actor.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    result = await session.execute(
        select(TicketAssignment).where(
            TicketAssignment.ticket_id == ticket_id,
            TicketAssignment.user_id == user_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    await emit_event(
        session,
        ticket_id,
        "ticket.unassigned",
        actor,
        prev_state={"user_id": user_id},
        new_state=None,
    )
    await session.delete(assignment)
    await session.commit()
