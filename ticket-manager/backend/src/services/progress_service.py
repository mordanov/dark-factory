from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.progress_update import ProgressUpdate
from src.models.ticket import Ticket
from src.models.ticket_assignment import TicketAssignment
from src.models.user import User
from src.schemas.progress import ProgressListResponse, ProgressUpdateResponse
from src.services.event_service import emit_event


async def submit_update(
    session: AsyncSession,
    ticket_id: UUID,
    actor: User,
    content: str,
) -> ProgressUpdateResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    assignment_result = await session.execute(
        select(TicketAssignment).where(
            TicketAssignment.ticket_id == ticket_id,
            TicketAssignment.user_id == actor.id,
        )
    )
    if assignment_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Must be an active assignee to submit progress",
        )

    existing_result = await session.execute(
        select(ProgressUpdate).where(
            ProgressUpdate.ticket_id == ticket_id,
            ProgressUpdate.user_id == actor.id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    prev_content = existing.content if existing else None

    if existing:
        existing.content = content
        await session.flush()
        record = existing
    else:
        record = ProgressUpdate(ticket_id=ticket_id, user_id=actor.id, content=content)
        session.add(record)
        await session.flush()

    await emit_event(
        session,
        ticket_id,
        "ticket.progress_updated",
        actor,
        prev_state={"content": prev_content} if prev_content is not None else None,
        new_state={"content": content},
    )
    await session.commit()
    await session.refresh(record)
    return ProgressUpdateResponse.model_validate(record)


async def list_updates(
    session: AsyncSession,
    ticket_id: UUID,
    actor: User,
) -> ProgressListResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    result = await session.execute(
        select(ProgressUpdate).where(ProgressUpdate.ticket_id == ticket_id)
    )
    updates = result.scalars().all()
    return ProgressListResponse(items=[ProgressUpdateResponse.model_validate(u) for u in updates])
