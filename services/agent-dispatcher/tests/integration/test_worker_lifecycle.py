"""Integration tests — US2: Agent Worker Lifecycle Registration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from src.repositories.worker_repository import AgentWorkerRepository
from src.services.capability_registry import AgentCapability
from src.services.worker_service import AgentWorkerService


def _backend_cap():
    return AgentCapability(
        role_id="backend",
        display_name="Backend",
        skill_file="backend.md",
        coordinator=False,
        capabilities=["python_backend"],
        fsm_ownership=["backend_development"],
        preferred_for=[],
        brainstorm_also_for=[],
        brainstorm_role="contributor",
    )


@pytest.fixture
async def worker_svc(db_session):
    with patch("src.services.worker_service.get_registry") as mock_reg:
        mock_reg.return_value.get_by_role_id.return_value = _backend_cap()
        yield AgentWorkerService(db_session)


async def test_register_creates_idle_worker(worker_svc, db_session):
    result = await worker_svc.register_worker("backend", "1.0", {"python_backend": 95})
    await db_session.commit()

    assert result["role_id"] == "backend"
    assert result["status"] == "idle"
    assert result["worker_id"] is not None


async def test_register_emits_lifecycle_event(worker_svc, db_session):
    result = await worker_svc.register_worker("backend", "1.0", {})
    await db_session.commit()

    repo = AgentWorkerRepository(db_session)
    worker = await repo.get_by_id_with_events(result["worker_id"])
    assert worker is not None
    events = worker.lifecycle_events
    assert any(e.event_type == "registered" for e in events)


async def test_register_rejects_unknown_role_id(db_session):
    with patch("src.services.worker_service.get_registry") as mock_reg:
        mock_reg.return_value.get_by_role_id.return_value = None
        svc = AgentWorkerService(db_session)
        with pytest.raises(ValueError, match="not found in capability registry"):
            await svc.register_worker("nonexistent-role", "1.0", {})


async def test_heartbeat_updates_timestamp(worker_svc, db_session):
    reg_result = await worker_svc.register_worker("backend", "1.0", {})
    worker_id = reg_result["worker_id"]
    await db_session.commit()

    hb_result = await worker_svc.record_heartbeat(worker_id, "backend", status=None)
    await db_session.commit()

    assert hb_result["acknowledged"] is True
    assert hb_result["next_heartbeat_deadline"] > datetime.now(UTC)


async def test_heartbeat_on_offline_worker_raises(worker_svc, db_session):
    repo = AgentWorkerRepository(db_session)
    worker = await repo.create("backend", "1.0", {})
    await repo.update_status(worker.id, "offline")
    await db_session.commit()

    with pytest.raises(LookupError):
        await worker_svc.record_heartbeat(worker.id, "backend", status=None)


async def test_drain_transitions_to_draining(worker_svc, db_session):
    reg_result = await worker_svc.register_worker("backend", "1.0", {})
    worker_id = reg_result["worker_id"]
    await db_session.commit()

    drain_result = await worker_svc.drain_worker(worker_id, "backend")
    await db_session.commit()

    assert drain_result["status"] == "draining"

    repo = AgentWorkerRepository(db_session)
    worker = await repo.get_by_id(worker_id)
    assert worker.status == "draining"


async def test_drain_emits_lifecycle_event(worker_svc, db_session):
    reg_result = await worker_svc.register_worker("backend", "1.0", {})
    worker_id = reg_result["worker_id"]
    await db_session.commit()

    await worker_svc.drain_worker(worker_id, "backend")
    await db_session.commit()

    repo = AgentWorkerRepository(db_session)
    worker = await repo.get_by_id_with_events(worker_id)
    event_types = [e.event_type for e in worker.lifecycle_events]
    assert "drain_requested" in event_types


async def test_liveness_sweep_marks_stale_worker_unhealthy(worker_svc, db_session):
    repo = AgentWorkerRepository(db_session)
    # Create a worker with a stale heartbeat
    worker = await repo.create("backend", "1.0", {})
    stale_time = datetime.now(UTC) - timedelta(minutes=5)
    await repo.update_heartbeat(worker.id)
    # Directly set a stale timestamp via SQL
    from sqlalchemy import update as sa_update
    from src.models.models import AgentWorkerRecord

    await db_session.execute(
        sa_update(AgentWorkerRecord)
        .where(AgentWorkerRecord.id == worker.id)
        .values(last_heartbeat_at=stale_time)
    )
    await db_session.commit()

    swept = await worker_svc.run_liveness_sweep(threshold_seconds=60)
    await db_session.commit()

    assert swept >= 1
    updated = await repo.get_by_id(worker.id)
    assert updated.status == "unhealthy"


async def test_list_workers_filter_by_status(worker_svc, db_session):
    reg_result = await worker_svc.register_worker("backend", "1.0", {})
    await db_session.commit()

    idle_workers = await worker_svc.list_workers(status_filter="idle")
    offline_workers = await worker_svc.list_workers(status_filter="offline")

    assert any(str(w.id) == str(reg_result["worker_id"]) for w in idle_workers)
    assert not any(str(w.id) == str(reg_result["worker_id"]) for w in offline_workers)


async def test_no_assignment_to_non_idle_worker(db_session):
    """resolve_capable_worker must not return draining or unhealthy workers."""
    repo = AgentWorkerRepository(db_session)
    worker = await repo.create("backend", "1.0", {"python_backend": 95})
    await repo.update_status(worker.id, "draining")
    await db_session.commit()

    backend_cap = _backend_cap()
    with patch("src.services.worker_service.get_registry") as mock_reg:
        mock_reg.return_value.get_by_capability.return_value = [backend_cap]
        svc = AgentWorkerService(db_session)
        result = await svc.resolve_capable_worker(["python_backend"])

    assert result is None
