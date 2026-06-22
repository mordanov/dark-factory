from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.orchestrator_audit_event import OrchestratorAuditEvent
from src.models.ticket import Ticket
from src.schemas.orchestrator import AuditEventCreate, AuditEventResponse, AuditLogResponse

log = structlog.get_logger(__name__)


async def create_audit_event(
    session: AsyncSession,
    ticket_id: UUID,
    body: AuditEventCreate,
) -> AuditEventResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    ts = body.timestamp if body.timestamp is not None else datetime.now(UTC)

    event = OrchestratorAuditEvent(
        ticket_id=ticket_id,
        event=body.event,
        actor=body.actor,
        from_state=body.from_state,
        to_state=body.to_state,
        details=body.details,
        timestamp=ts,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)

    log.info(
        "audit.created",
        ticket_id=str(ticket_id),
        audit_event=body.event,
        actor=body.actor,
        from_state=body.from_state,
        to_state=body.to_state,
    )

    return AuditEventResponse.model_validate(event)


async def get_audit_log(
    session: AsyncSession,
    ticket_id: UUID,
) -> AuditLogResponse:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    result = await session.execute(
        select(OrchestratorAuditEvent)
        .where(OrchestratorAuditEvent.ticket_id == ticket_id)
        .order_by(OrchestratorAuditEvent.timestamp.asc())
    )
    events = result.scalars().all()

    return AuditLogResponse(
        ticket_id=ticket_id,
        entries=[AuditEventResponse.model_validate(e) for e in events],
    )
