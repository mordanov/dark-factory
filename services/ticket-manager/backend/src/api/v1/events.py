from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.ticket import Ticket
from src.models.ticket_event import TicketEvent
from src.models.user import User
from src.schemas.event import EventListResponse, TicketEventResponse
from src.schemas.ticket import UserSummary

router = APIRouter(prefix="/tickets", tags=["Events"])


@router.get("/{ticket_id}/events", response_model=EventListResponse)
async def list_events(
    ticket_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> EventListResponse:
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    result = await db.execute(
        select(TicketEvent)
        .where(TicketEvent.ticket_id == ticket_id)
        .options(selectinload(TicketEvent.actor))
        .order_by(TicketEvent.occurred_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    events = result.scalars().all()

    items = [
        TicketEventResponse(
            id=e.id,
            ticket_id=e.ticket_id,
            event_type=e.event_type,
            actor=UserSummary(id=e.actor.id, email=e.actor.email, role=e.actor.role),
            prev_state=e.prev_state,
            new_state=e.new_state,
            metadata=e.metadata_,
            occurred_at=e.occurred_at,
        )
        for e in events
    ]
    return EventListResponse(items=items)
