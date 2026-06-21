"""Audit log repository — append-only."""
from __future__ import annotations
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import AuditLog


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def append(
        self,
        *,
        ticket_id: str,
        project_id: str,
        action: str,
        details: str,
        from_state: str | None = None,
        to_state: str | None = None,
        assigned_agent: str | None = None,
        blocked_reason: str | None = None,
        override_logged: bool = False,
        job_id: uuid.UUID | None = None,
        decision_payload: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            job_id=job_id,
            ticket_id=ticket_id,
            project_id=project_id,
            action=action,
            from_state=from_state,
            to_state=to_state,
            assigned_agent=assigned_agent,
            blocked_reason=blocked_reason,
            override_logged=override_logged,
            details=details,
            decision_payload=decision_payload,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry

    async def list_for_ticket(
        self, ticket_id: str, offset: int = 0, limit: int = 100
    ) -> tuple[list[AuditLog], int]:
        count = (await self._db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.ticket_id == ticket_id)
        )).scalar_one()
        entries = list((await self._db.execute(
            select(AuditLog)
            .where(AuditLog.ticket_id == ticket_id)
            .order_by(AuditLog.created_at.asc())
            .offset(offset).limit(limit)
        )).scalars().all())
        return entries, count
