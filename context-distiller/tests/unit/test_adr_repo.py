"""Unit tests for MemoryRepository — ADR operations."""
import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from src.core.exceptions import ConflictError, NotFoundError
from src.repositories.memory_repo import MemoryRepository


@pytest_asyncio.fixture
async def repo():
    client = AsyncMongoMockClient()
    db = client["test_db"]
    return MemoryRepository(db)


async def test_create_adr_first_number(repo):
    adr_id = await repo.create_adr(
        "proj-1",
        {"title": "Use PG", "summary": "PG for queue", "content": "# ADR\n...", "ticket_id": "T-001"},
    )
    assert adr_id == "ADR-001"


async def test_create_adr_increments_number(repo):
    await repo.create_adr(
        "proj-1",
        {"title": "First", "summary": "s", "content": "c", "ticket_id": "T-001"},
    )
    adr_id = await repo.create_adr(
        "proj-1",
        {"title": "Second", "summary": "s", "content": "c", "ticket_id": "T-002"},
    )
    assert adr_id == "ADR-002"


async def test_create_adr_default_status_proposed(repo):
    await repo.create_adr(
        "proj-1",
        {"title": "T", "summary": "s", "content": "c", "ticket_id": "T-001"},
    )
    adr = await repo.get_adr("proj-1", "ADR-001")
    assert adr["status"] == "proposed"


async def test_valid_status_transition_proposed_to_accepted(repo):
    await repo.create_adr(
        "proj-1",
        {"title": "T", "summary": "s", "content": "c", "ticket_id": "T-001"},
    )
    result = await repo.update_adr_status("proj-1", "ADR-001", "accepted")
    assert result["status"] == "accepted"


async def test_valid_status_transition_accepted_to_superseded(repo):
    await repo.create_adr(
        "proj-1",
        {"title": "T", "summary": "s", "content": "c", "ticket_id": "T-001"},
    )
    await repo.update_adr_status("proj-1", "ADR-001", "accepted")
    result = await repo.update_adr_status("proj-1", "ADR-001", "superseded")
    assert result["status"] == "superseded"


async def test_invalid_status_transition_raises_conflict(repo):
    await repo.create_adr(
        "proj-1",
        {"title": "T", "summary": "s", "content": "c", "ticket_id": "T-001"},
    )
    await repo.update_adr_status("proj-1", "ADR-001", "accepted")
    with pytest.raises(ConflictError):
        await repo.update_adr_status("proj-1", "ADR-001", "proposed")


async def test_update_adr_status_not_found_raises(repo):
    with pytest.raises(NotFoundError):
        await repo.update_adr_status("proj-1", "ADR-999", "accepted")


async def test_get_adrs_filter_by_status(repo):
    await repo.create_adr(
        "proj-1",
        {"title": "T1", "summary": "s", "content": "c", "ticket_id": "T-001"},
    )
    await repo.create_adr(
        "proj-1",
        {"title": "T2", "summary": "s", "content": "c", "ticket_id": "T-002"},
    )
    await repo.update_adr_status("proj-1", "ADR-001", "accepted")

    accepted = await repo.get_adrs("proj-1", status_filter="accepted")
    assert len(accepted) == 1
    assert accepted[0]["_id"] == "ADR-001"

    proposed = await repo.get_adrs("proj-1", status_filter="proposed")
    assert len(proposed) == 1
    assert proposed[0]["_id"] == "ADR-002"


async def test_get_adrs_all(repo):
    await repo.create_adr(
        "proj-1",
        {"title": "T1", "summary": "s", "content": "c", "ticket_id": "T-001"},
    )
    await repo.create_adr(
        "proj-1",
        {"title": "T2", "summary": "s", "content": "c", "ticket_id": "T-002"},
    )
    all_adrs = await repo.get_adrs("proj-1", status_filter="all")
    assert len(all_adrs) == 2
