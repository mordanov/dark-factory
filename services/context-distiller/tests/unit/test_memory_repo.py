"""Unit tests for MemoryRepository — project_memory operations."""

from unittest.mock import patch

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient
from src.repositories.memory_repo import MemoryRepository

_BASE_YAML = (
    "project_id: {pid}\nlast_updated: {ts}\nlast_ticket_id: {tid}\n"
    "architecture: []\nrecent_changes: []\nopen_risks: []\nknown_constraints: []\n"
    "tech_stack: {{backend: '', frontend: '', database: '', infra: ''}}"
)


@pytest_asyncio.fixture
async def repo():
    client = AsyncMongoMockClient()
    db = client["test_db"]
    return MemoryRepository(db), db


async def test_fresh_start_no_prior_memory(repo):
    repo_inst, db = repo
    yaml = _BASE_YAML.format(pid="proj-1", ts="now", tid="T-001")
    await repo_inst.archive_then_write("proj-1", yaml, "T-001")
    doc = await repo_inst.get_memory("proj-1")
    assert doc is not None
    assert doc["version"] == 1
    # First run: no history
    history = await db.project_memory_history.count_documents({"project_id": "proj-1"})
    assert history == 0


async def test_archive_before_overwrite(repo):
    repo_inst, db = repo
    yaml1 = _BASE_YAML.format(pid="proj-1", ts="t1", tid="T-001")
    yaml2 = _BASE_YAML.format(pid="proj-1", ts="t2", tid="T-002")

    await repo_inst.archive_then_write("proj-1", yaml1, "T-001")
    await repo_inst.archive_then_write("proj-1", yaml2, "T-002")

    # Version 1 should be in history
    history = await db.project_memory_history.find({"project_id": "proj-1"}).to_list(None)
    assert len(history) == 1
    assert history[0]["version"] == 1
    assert history[0]["content"] == yaml1

    # Current should be version 2
    current = await repo_inst.get_memory("proj-1")
    assert current["version"] == 2
    assert current["content"] == yaml2


async def test_version_increments_monotonically(repo):
    repo_inst, db = repo
    yaml = _BASE_YAML.format(pid="p", ts="t", tid="T-00{n}")
    for i in range(1, 5):
        await repo_inst.archive_then_write("proj-1", yaml, f"T-{i:03d}")
    doc = await repo_inst.get_memory("proj-1")
    assert doc["version"] == 4


async def test_history_pruned_to_keep(repo):
    repo_inst, db = repo
    yaml = _BASE_YAML.format(pid="p", ts="t", tid="T")

    with patch("src.repositories.memory_repo.get_settings") as mock_settings:
        mock_settings.return_value.distiller_memory_history_keep = 2
        for i in range(1, 5):
            await repo_inst.archive_then_write("proj-1", yaml, f"T-{i:03d}")

    count = await db.project_memory_history.count_documents({"project_id": "proj-1"})
    assert count <= 2


async def test_get_memory_returns_none_for_missing(repo):
    repo_inst, _ = repo
    doc = await repo_inst.get_memory("nonexistent")
    assert doc is None
