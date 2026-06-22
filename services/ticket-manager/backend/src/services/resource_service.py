from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ticket import Ticket
from src.models.user import User
from src.schemas.resource import TicketResourceIncrementResponse
from src.services.event_service import emit_event

_log = structlog.get_logger(__name__)


async def increment_resources(
    session: AsyncSession,
    ticket_id: UUID,
    actor: User,
    time_delta: int,
    token_delta: int,
) -> TicketResourceIncrementResponse:
    if time_delta == 0 and token_delta == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of time_spent_delta or tokens_consumed_delta must be > 0",
        )

    ticket_result = await session.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.deleted_at.is_(None)).with_for_update()
    )
    ticket = ticket_result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    prev_state = {"time_spent": ticket.time_spent, "tokens_consumed": ticket.tokens_consumed}

    await session.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id)
        .values(
            time_spent=Ticket.time_spent + time_delta,
            tokens_consumed=Ticket.tokens_consumed + token_delta,
        )
    )
    await session.refresh(ticket)

    event = await emit_event(
        session,
        ticket_id,
        "ticket.resources_incremented",
        actor,
        prev_state=prev_state,
        new_state={
            "time_spent": ticket.time_spent,
            "tokens_consumed": ticket.tokens_consumed,
            "time_spent_delta": time_delta,
            "tokens_consumed_delta": token_delta,
        },
    )
    await session.flush()
    await session.commit()
    await session.refresh(event)

    _log.info(
        "ticket_resources_incremented",
        ticket_id=str(ticket_id),
        actor_id=str(actor.id),
        time_spent_delta=time_delta,
        tokens_consumed_delta=token_delta,
        time_spent_total=ticket.time_spent,
        tokens_consumed_total=ticket.tokens_consumed,
    )

    return TicketResourceIncrementResponse(
        ticket_id=ticket_id,
        time_spent=ticket.time_spent,
        tokens_consumed=ticket.tokens_consumed,
        event_id=event.id,
    )
