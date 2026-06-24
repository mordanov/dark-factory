from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import UserClaims
from src.models.ticket_event import TicketEvent
from src.models.user import UserRole


async def emit_event(
    session: AsyncSession,
    ticket_id: UUID,
    event_type: str,
    actor: UserClaims,
    prev_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> TicketEvent:
    actor_role = UserRole.administrator if actor.is_admin else UserRole.user
    event = TicketEvent(
        ticket_id=ticket_id,
        event_type=event_type,
        actor_id=actor.sub,
        actor_role=actor_role,
        prev_state=prev_state,
        new_state=new_state,
        metadata_=metadata,
    )
    session.add(event)
    return event
