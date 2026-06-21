"""MongoDB repository for project_memory, project_memory_history, and adrs."""
from __future__ import annotations
import re
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.config import get_settings
from src.core.exceptions import ConflictError, NotFoundError

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"accepted", "superseded"},
    "accepted": {"superseded"},
    "superseded": set(),
}

_IMMUTABLE_ADR_FIELDS = {"title", "content", "project_id", "ticket_id"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # project_memory
    # ------------------------------------------------------------------

    async def get_memory(self, project_id: str) -> dict | None:
        return await self._db.project_memory.find_one({"_id": project_id})

    async def archive_then_write(
        self, project_id: str, yaml_content: str, ticket_id: str
    ) -> None:
        settings = get_settings()
        current = await self.get_memory(project_id)

        if current:
            await self._db.project_memory_history.insert_one(
                {
                    "project_id": project_id,
                    "version": current["version"],
                    "content": current["content"],
                    "ticket_id": current.get("last_ticket_id", ""),
                    "created_at": _now_iso(),
                }
            )
            await self._prune_history(project_id, settings.distiller_memory_history_keep)
            new_version = current["version"] + 1
        else:
            new_version = 1

        await self._db.project_memory.replace_one(
            {"_id": project_id},
            {
                "_id": project_id,
                "content": yaml_content,
                "version": new_version,
                "last_ticket_id": ticket_id,
                "updated_at": _now_iso(),
            },
            upsert=True,
        )

    async def _prune_history(self, project_id: str, keep: int) -> None:
        cursor = (
            self._db.project_memory_history.find({"project_id": project_id})
            .sort("version", -1)
            .skip(keep)
        )
        old_docs = await cursor.to_list(length=None)
        if old_docs:
            ids = [d["_id"] for d in old_docs]
            await self._db.project_memory_history.delete_many({"_id": {"$in": ids}})

    # ------------------------------------------------------------------
    # adrs
    # ------------------------------------------------------------------

    async def _next_adr_number(self, project_id: str) -> int:
        last = await self._db.adrs.find_one(
            {"project_id": project_id},
            sort=[("_id", -1)],
        )
        if not last:
            return 1
        match = re.match(r"ADR-(\d+)", last["_id"])
        return int(match.group(1)) + 1 if match else 1

    async def get_adrs(
        self, project_id: str, status_filter: str = "accepted"
    ) -> list[dict]:
        query: dict = {"project_id": project_id}
        if status_filter != "all":
            query["status"] = status_filter
        cursor = self._db.adrs.find(query).sort("_id", 1)
        return await cursor.to_list(length=None)

    async def get_adr(self, project_id: str, adr_id: str) -> dict | None:
        return await self._db.adrs.find_one({"_id": adr_id, "project_id": project_id})

    async def create_adr(self, project_id: str, data: dict) -> str:
        num = await self._next_adr_number(project_id)
        adr_id = f"ADR-{num:03d}"
        now = _now_iso()
        doc = {
            "_id": adr_id,
            "project_id": project_id,
            "title": data["title"],
            "status": "proposed",
            "summary": data.get("summary", ""),
            "content": data["content"],
            "ticket_id": data["ticket_id"],
            "created_at": now,
            "updated_at": now,
        }
        await self._db.adrs.insert_one(doc)
        return adr_id

    async def update_adr_status(
        self, project_id: str, adr_id: str, new_status: str
    ) -> dict:
        adr = await self.get_adr(project_id, adr_id)
        if not adr:
            raise NotFoundError(f"ADR {adr_id} not found")
        current_status = adr["status"]
        if new_status not in _VALID_TRANSITIONS.get(current_status, set()):
            raise ConflictError(
                f"Invalid status transition: {current_status} → {new_status}"
            )
        await self._db.adrs.update_one(
            {"_id": adr_id, "project_id": project_id},
            {"$set": {"status": new_status, "updated_at": _now_iso()}},
        )
        return {"adr_id": adr_id, "status": new_status}
