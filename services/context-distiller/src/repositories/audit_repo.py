"""Audit log repository — read-only."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AuditLog


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_audit_trail(self, ticket_id: str) -> list[dict]:
        result = await self._db.execute(
            select(AuditLog)
            .where(AuditLog.ticket_id == ticket_id)
            .order_by(AuditLog.created_at.asc())
        )
        rows = result.scalars().all()
        return [
            {
                "action": r.action,
                "from_state": r.from_state,
                "to_state": r.to_state,
                "assigned_agent": r.assigned_agent,
                "details": r.details,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
