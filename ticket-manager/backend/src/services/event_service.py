from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ticket_event import TicketEvent
from src.models.user import User


async def emit_event(
    session: AsyncSession,
    ticket_id: UUID,
    event_type: str,
    actor: User,
    prev_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> TicketEvent:
    event = TicketEvent(
        ticket_id=ticket_id,
        event_type=event_type,
        actor_id=actor.id,
        actor_role=actor.role,
        prev_state=prev_state,
        new_state=new_state,
        metadata_=metadata,
    )
    session.add(event)
    return event
