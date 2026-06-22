"""DataCollector — assembles all inputs for a distillation call."""

from __future__ import annotations

from dataclasses import dataclass, field

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.audit_repo import AuditRepository
from src.repositories.memory_repo import MemoryRepository
from src.services.tm_client import TMClient


@dataclass
class CollectedContext:
    ticket_id: str
    project_id: str
    ticket: dict
    audit_trail: list[dict]
    current_memory: str | None
    adr_refs: list[dict] = field(default_factory=list)


class DataCollector:
    def __init__(
        self,
        tm_client: TMClient,
        db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
    ) -> None:
        self._tm = tm_client
        self._audit_repo = AuditRepository(db)
        self._memory_repo = MemoryRepository(mongo_db)

    async def collect(self, ticket_id: str, project_id: str) -> CollectedContext:
        ticket = await self._tm.get_ticket(ticket_id)
        tm_events = await self._tm.get_ticket_events(ticket_id)
        pg_trail = await self._audit_repo.get_audit_trail(ticket_id)

        audit_trail = pg_trail + [
            {
                "action": e.get("event_type", "TM_EVENT"),
                "details": str(e.get("new_state", "")),
                "created_at": str(e.get("occurred_at", "")),
            }
            for e in tm_events
        ]

        memory_doc = await self._memory_repo.get_memory(project_id)
        current_memory = memory_doc["content"] if memory_doc else None

        adrs = await self._memory_repo.get_adrs(project_id, status_filter="accepted")
        adr_refs = [{"id": a["_id"], "title": a.get("title", "")} for a in adrs]

        return CollectedContext(
            ticket_id=ticket_id,
            project_id=project_id,
            ticket=ticket,
            audit_trail=audit_trail,
            current_memory=current_memory,
            adr_refs=adr_refs,
        )
