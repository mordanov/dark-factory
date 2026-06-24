from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ticket import Ticket
from src.models.ticket_assignment import TicketAssignment
from src.models.ticket_event import TicketEvent
from src.models.user import User
from src.schemas.ticket import TokensSpentIncrementResponse
from src.services.event_service import emit_event


async def increment_tokens_spent(
    session: AsyncSession,
    ticket_id: UUID,
    amount: int,
    actor: User,
) -> TokensSpentIncrementResponse:
    ticket_result = await session.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.deleted_at.is_(None)).with_for_update()
    )
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    assignments_result = await session.execute(
        select(TicketAssignment).where(TicketAssignment.ticket_id == ticket_id)
    )
    assignee_ids = {a.user_id for a in assignments_result.scalars().all()}
    if actor.id not in assignee_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only current assignees may increment tokens_spent",
        )

    prev_value = ticket.tokens_spent
    ticket.tokens_spent = prev_value + amount

    event = await emit_event(
        session,
        ticket_id,
        "ticket.tokens_spent_incremented",
        actor,
        prev_state={"tokens_spent": prev_value},
        new_state={"tokens_spent": ticket.tokens_spent},
        metadata={"amount_added": amount},
    )
    await session.commit()
    await session.refresh(event)

    return TokensSpentIncrementResponse(
        ticket_id=ticket_id,
        tokens_spent=ticket.tokens_spent,
        amount_added=amount,
        event_id=event.id,
    )
