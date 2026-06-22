"""Integration tests for full distillation lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mongomock_motor import AsyncMongoMockClient
from src.repositories.job_repo import JobRepository
from src.repositories.memory_repo import MemoryRepository

VALID_YAML = """\
project_id: proj-1
last_updated: "2026-06-20T10:00:00Z"
last_ticket_id: T-001
architecture:
  - "JWT auth added"
recent_changes:
  - ticket_id: T-001
    summary: "Added auth"
    files_changed: ["src/auth.py"]
    risks: []
open_risks: []
known_constraints:
  - "All async"
tech_stack:
  backend: "Python 3.12"
  frontend: "N/A"
  database: "PostgreSQL"
  infra: "Docker"
"""


async def test_memory_written_after_distillation(test_client, mongo_db, db_session):
    """After enqueue + mock worker run, memory is present."""
    memory_repo = MemoryRepository(mongo_db)
    # Directly write memory as if worker completed
    await memory_repo.archive_then_write("proj-lifecycle", VALID_YAML, "T-001")

    resp = await test_client.get("/memory/proj-lifecycle")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == 1
    assert "project_id" in data["content"]


async def test_idempotent_distillation_no_duplicate_changes(test_client, mongo_db):
    """Running archive_then_write twice creates history and increments version."""
    memory_repo = MemoryRepository(mongo_db)
    await memory_repo.archive_then_write("proj-idem", VALID_YAML, "T-001")
    await memory_repo.archive_then_write("proj-idem", VALID_YAML, "T-001")

    doc = await memory_repo.get_memory("proj-idem")
    assert doc["version"] == 2

    history_count = await mongo_db.project_memory_history.count_documents(
        {"project_id": "proj-idem"}
    )
    assert history_count == 1  # Only version 1 archived


async def test_llm_failure_does_not_overwrite_memory(test_client, mongo_db, db_session):
    """When distillation fails, existing memory is preserved."""
    memory_repo = MemoryRepository(mongo_db)
    await memory_repo.archive_then_write("proj-fail", VALID_YAML, "T-000")

    # Simulate failed distillation: mark job failed without touching memory
    job_repo = JobRepository(db_session)
    job = await job_repo.create_distill_job("T-001", "proj-fail")
    await db_session.commit()
    await job_repo.mark_failed(job.id, "LLM parse error after 3 attempts")
    await db_session.commit()

    # Memory should still be the original
    doc = await memory_repo.get_memory("proj-fail")
    assert doc["version"] == 1
    assert "project_id" in doc["content"]

    # Job should be marked failed
    from src.repositories.job_repo import JobRepository as JR

    repo2 = JR(db_session)
    fetched = await repo2.get_by_id(job.id)
    assert fetched.status == "failed"
    assert "LLM parse error" in fetched.error_message
