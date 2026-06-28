"""Worker service — agent worker lifecycle and capability-based resolution."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.worker_repository import AgentWorkerRepository
from src.services.capability_registry import AgentCapability, get_registry

logger = structlog.get_logger(__name__)

_HEARTBEAT_INTERVAL_SECONDS = 30
_LIVENESS_MULTIPLIER = 2.0


def _liveness_threshold(
    multiplier: float | None = None,
    interval: int | None = None,
) -> datetime:
    _mult = multiplier if multiplier is not None else _LIVENESS_MULTIPLIER
    _int = interval if interval is not None else _HEARTBEAT_INTERVAL_SECONDS
    gap = timedelta(seconds=_int * _mult)
    return datetime.now(UTC) - gap


class AgentWorkerService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = AgentWorkerRepository(db)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register_worker(
        self,
        role_id: str,
        version: str,
        capabilities_snapshot: dict,
    ) -> dict:
        registry = get_registry()
        if registry.get_by_role_id(role_id) is None:
            raise ValueError(f"role_id {role_id!r} not found in capability registry")

        worker = await self._repo.create(role_id, version, capabilities_snapshot)
        await self._repo.write_lifecycle_event(
            worker.id, role_id, "registered", {"version": version}
        )
        logger.info("Worker registered", role_id=role_id, worker_id=str(worker.id))
        return {
            "worker_id": worker.id,
            "role_id": worker.role_id,
            "status": worker.status,
            "registered_at": worker.registered_at,
        }

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def record_heartbeat(
        self,
        worker_id: uuid.UUID,
        role_id: str,
        status: str | None,
    ) -> dict:
        worker = await self._repo.get_by_id(worker_id)
        if worker is None or worker.status == "offline":
            raise LookupError(f"Worker {worker_id} not found or already offline")

        await self._repo.update_heartbeat(worker_id, new_status=status)
        next_deadline = datetime.now(UTC) + timedelta(
            seconds=_HEARTBEAT_INTERVAL_SECONDS * _LIVENESS_MULTIPLIER
        )
        return {"acknowledged": True, "next_heartbeat_deadline": next_deadline}

    # ------------------------------------------------------------------
    # Drain
    # ------------------------------------------------------------------

    async def drain_worker(self, worker_id: uuid.UUID, role_id: str) -> dict:
        worker = await self._repo.get_by_id(worker_id)
        if worker is None:
            raise LookupError(f"Worker {worker_id} not found")

        await self._repo.update_status(worker_id, "draining")
        await self._repo.write_lifecycle_event(worker_id, role_id, "drain_requested")
        return {"worker_id": worker_id, "status": "draining", "offline_at": None}

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_workers(
        self,
        status_filter: str | None = None,
        role_id_filter: str | None = None,
    ) -> list:
        return await self._repo.list_all(status_filter, role_id_filter)

    # ------------------------------------------------------------------
    # Capability-based resolution (US1)
    # ------------------------------------------------------------------

    async def resolve_capable_worker(
        self,
        required_capabilities: list[str],
        min_confidence: int = 0,
    ) -> AgentCapability | None:
        """Return the best-matched available agent for the given required capabilities.

        Returns None when no capable idle worker is found (caller should fall back
        to static assignment).
        """
        if not required_capabilities:
            return None

        registry = get_registry()
        capable_agents = registry.get_by_capability(required_capabilities, min_confidence)
        if not capable_agents:
            logger.info(
                "No agents declared required capabilities",
                required=required_capabilities,
            )
            return None

        capable_role_ids = {a.role_id for a in capable_agents}
        idle_workers = await self._repo.list_all(status_filter="idle")
        idle_role_ids = {w.role_id for w in idle_workers if w.role_id in capable_role_ids}

        if not idle_role_ids:
            logger.info(
                "No idle workers available for required capabilities",
                required=required_capabilities,
            )
            return None

        # Rank by: (1) count of required caps covered, (2) avg confidence for those caps
        def _score(agent: AgentCapability) -> tuple[int, float]:
            covered = sum(1 for c in required_capabilities if c in agent.capabilities)
            avg_conf = sum(
                agent.confidence.get(c, 100) for c in required_capabilities
            ) / len(required_capabilities)
            return (covered, avg_conf)

        candidates = [a for a in capable_agents if a.role_id in idle_role_ids]
        candidates.sort(key=_score, reverse=True)
        return candidates[0]

    # ------------------------------------------------------------------
    # Liveness sweep
    # ------------------------------------------------------------------

    async def run_liveness_sweep(
        self, threshold_seconds: float | None = None
    ) -> int:
        """Mark workers with stale heartbeats as unhealthy.

        Returns the count of workers transitioned.
        """
        if threshold_seconds is not None:
            threshold = datetime.now(UTC) - timedelta(seconds=threshold_seconds)
        else:
            threshold = _liveness_threshold()

        stale = await self._repo.get_stale(threshold)
        for worker in stale:
            await self._repo.update_status(worker.id, "unhealthy")
            await self._repo.write_lifecycle_event(
                worker.id,
                worker.role_id,
                "offline_liveness",
                {"last_heartbeat_at": worker.last_heartbeat_at.isoformat()},
            )
            logger.warning(
                "Worker marked unhealthy (liveness sweep)",
                worker_id=str(worker.id),
                role_id=worker.role_id,
                last_heartbeat_at=worker.last_heartbeat_at.isoformat(),
            )
        return len(stale)
