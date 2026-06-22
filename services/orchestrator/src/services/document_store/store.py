"""Document Store service — reads/writes project_memory and ADRs in MongoDB."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.config import get_settings
from src.schemas.schemas import AdrSummary, ProjectMemoryResponse

settings = get_settings()

_MEMORY_COL = "project_memory"
_MEMORY_HISTORY_COL = "project_memory_history"
_ADR_COL = "adrs"


class DocumentStore:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Project Memory
    # ------------------------------------------------------------------

    async def get_memory(self, project_id: str) -> ProjectMemoryResponse | None:
        doc = await self._db[_MEMORY_COL].find_one({"_id": project_id})
        if not doc:
            return None
        return ProjectMemoryResponse(
            project_id=project_id,
            content=doc.get("content", ""),
            version=doc.get("version", 0),
            last_ticket_id=doc.get("last_ticket_id"),
            updated_at=doc.get("updated_at"),
        )

    async def save_memory(
        self, project_id: str, content: str, ticket_id: str
    ) -> ProjectMemoryResponse:
        now = datetime.now(UTC)
        existing = await self._db[_MEMORY_COL].find_one({"_id": project_id})
        old_version = existing.get("version", 0) if existing else 0
        new_version = old_version + 1

        # Keep history
        if existing:
            await self._db[_MEMORY_HISTORY_COL].insert_one(
                {
                    "project_id": project_id,
                    "version": old_version,
                    "content": existing.get("content", ""),
                    "ticket_id": existing.get("last_ticket_id"),
                    "created_at": now,
                }
            )
            # Prune history
            keep = settings.distiller_memory_history_keep
            history_count = await self._db[_MEMORY_HISTORY_COL].count_documents(
                {"project_id": project_id}
            )
            if history_count > keep:
                oldest_docs = (
                    await self._db[_MEMORY_HISTORY_COL]
                    .find({"project_id": project_id})
                    .sort("version", 1)
                    .limit(history_count - keep)
                    .to_list(None)
                )
                ids_to_delete = [d["_id"] for d in oldest_docs]
                await self._db[_MEMORY_HISTORY_COL].delete_many({"_id": {"$in": ids_to_delete}})

        await self._db[_MEMORY_COL].replace_one(
            {"_id": project_id},
            {
                "_id": project_id,
                "content": content,
                "version": new_version,
                "last_ticket_id": ticket_id,
                "updated_at": now,
            },
            upsert=True,
        )
        return ProjectMemoryResponse(
            project_id=project_id,
            content=content,
            version=new_version,
            last_ticket_id=ticket_id,
            updated_at=now,
        )

    # ------------------------------------------------------------------
    # ADRs
    # ------------------------------------------------------------------

    async def list_adrs(
        self,
        project_id: str,
        status_filter: str = "all",
        domain_filter: str | None = None,
    ) -> list[AdrSummary]:
        query: dict = {"project_id": project_id}
        if status_filter != "all":
            query["status"] = status_filter
        if domain_filter:
            query["domain"] = domain_filter
        cursor = self._db[_ADR_COL].find(query).sort("adr_number", 1)
        docs = await cursor.to_list(length=200)
        return [
            AdrSummary(
                id=d["_id"],
                project_id=d["project_id"],
                title=d.get("title", ""),
                status=d.get("status", "proposed"),
                summary=d.get("summary"),
                ticket_id=d.get("ticket_id"),
                created_at=d.get("created_at"),
            )
            for d in docs
        ]

    async def next_adr_number(self, project_id: str) -> int:
        """Return the next ADR number for a project (1-based)."""
        last = await self._db[_ADR_COL].find_one(
            {"project_id": project_id}, sort=[("adr_number", -1)]
        )
        return (last["adr_number"] + 1) if last else 1

    async def save_adr(self, project_id: str, content: str, ticket_id: str) -> str:
        """Parse the ADR markdown, extract metadata, persist. Returns ADR id."""
        number = await self.next_adr_number(project_id)
        adr_id = f"ADR-{number:03d}"
        now = datetime.now(UTC)

        title = _extract_adr_title(content) or adr_id
        summary = _extract_adr_section(content, "Decision") or ""

        await self._db[_ADR_COL].insert_one(
            {
                "_id": adr_id,
                "project_id": project_id,
                "adr_number": number,
                "title": title,
                "status": "proposed",
                "summary": summary[:500],
                "content": content,
                "ticket_id": ticket_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        return adr_id

    async def update_adr_status(self, adr_id: str, status: str) -> None:
        await self._db[_ADR_COL].update_one(
            {"_id": adr_id},
            {"$set": {"status": status, "updated_at": datetime.now(UTC)}},
        )


def _extract_adr_title(content: str) -> str | None:
    m = re.search(r"^#\s+ADR-\d+:\s+(.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else None


def _extract_adr_section(content: str, section: str) -> str | None:
    m = re.search(rf"##\s+{section}\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    return m.group(1).strip() if m else None
