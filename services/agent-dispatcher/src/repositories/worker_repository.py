"""Repository for AgentWorkerRecord and AgentLifecycleEvent."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.models import AgentLifecycleEvent, AgentWorkerRecord


class AgentWorkerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        role_id: str,
        version: str,
        capabilities_snapshot: dict,
    ) -> AgentWorkerRecord:
        worker = AgentWorkerRecord(
            role_id=role_id,
            version=version,
            capabilities_snapshot=capabilities_snapshot,
            status="idle",
        )
        self.db.add(worker)
        await self.db.flush()
        await self.db.refresh(worker)
        return worker

    async def get_by_id(self, worker_id: uuid.UUID) -> AgentWorkerRecord | None:
        result = await self.db.execute(
            select(AgentWorkerRecord).where(AgentWorkerRecord.id == worker_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_events(self, worker_id: uuid.UUID) -> AgentWorkerRecord | None:
        result = await self.db.execute(
            select(AgentWorkerRecord)
            .where(AgentWorkerRecord.id == worker_id)
            .options(selectinload(AgentWorkerRecord.lifecycle_events))
        )
        return result.scalar_one_or_none()

    async def get_by_role_status(self, role_id: str, status: str) -> list[AgentWorkerRecord]:
        result = await self.db.execute(
            select(AgentWorkerRecord).where(
                AgentWorkerRecord.role_id == role_id,
                AgentWorkerRecord.status == status,
            )
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        worker_id: uuid.UUID,
        new_status: str,
        offline_at: datetime | None = None,
    ) -> None:
        values: dict = {"status": new_status}
        if offline_at is not None:
            values["offline_at"] = offline_at
        await self.db.execute(
            update(AgentWorkerRecord).where(AgentWorkerRecord.id == worker_id).values(**values)
        )

    async def update_heartbeat(self, worker_id: uuid.UUID, new_status: str | None = None) -> None:
        values: dict = {"last_heartbeat_at": datetime.now(UTC)}
        if new_status is not None:
            values["status"] = new_status
        await self.db.execute(
            update(AgentWorkerRecord).where(AgentWorkerRecord.id == worker_id).values(**values)
        )

    async def list_all(
        self,
        status_filter: str | None = None,
        role_id_filter: str | None = None,
    ) -> list[AgentWorkerRecord]:
        query = select(AgentWorkerRecord)
        if status_filter:
            query = query.where(AgentWorkerRecord.status == status_filter)
        if role_id_filter:
            query = query.where(AgentWorkerRecord.role_id == role_id_filter)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_stale(self, threshold_dt: datetime) -> list[AgentWorkerRecord]:
        """Return non-offline workers with last_heartbeat_at < threshold_dt."""
        result = await self.db.execute(
            select(AgentWorkerRecord).where(
                AgentWorkerRecord.last_heartbeat_at < threshold_dt,
                AgentWorkerRecord.status.not_in(["offline"]),
            )
        )
        return list(result.scalars().all())

    async def write_lifecycle_event(
        self,
        worker_id: uuid.UUID,
        role_id: str,
        event_type: str,
        metadata: dict | None = None,
    ) -> AgentLifecycleEvent:
        event = AgentLifecycleEvent(
            worker_id=worker_id,
            role_id=role_id,
            event_type=event_type,
            event_metadata=metadata or {},
        )
        self.db.add(event)
        await self.db.flush()
        return event
