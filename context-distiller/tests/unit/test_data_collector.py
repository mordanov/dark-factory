"""Unit tests for DataCollector."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from mongomock_motor import AsyncMongoMockClient

from src.core.exceptions import UpstreamError
from src.services.data_collector import DataCollector


@pytest.fixture
def mongo_db():
    client = AsyncMongoMockClient()
    return client["test_db"]


def make_collector(mongo_db, ticket=None, events=None, tm_side_effect=None):
    mock_tm = AsyncMock()
    if tm_side_effect:
        mock_tm.get_ticket = AsyncMock(side_effect=tm_side_effect)
    else:
        mock_tm.get_ticket = AsyncMock(return_value=ticket or {"id": "T-001", "title": "Test"})
    mock_tm.get_ticket_events = AsyncMock(return_value=events or [])

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

    return DataCollector(mock_tm, mock_db, mongo_db)


async def test_collect_success(mongo_db):
    collector = make_collector(
        mongo_db,
        ticket={"id": "T-001", "title": "Add auth"},
        events=[{"event_type": "STATUS_CHANGE", "new_state": {"status": "done"}, "occurred_at": "2026-06-20T10:00:00Z"}],
    )
    ctx = await collector.collect("T-001", "proj-1")
    assert ctx.ticket_id == "T-001"
    assert ctx.project_id == "proj-1"
    assert ctx.ticket["title"] == "Add auth"
    assert ctx.current_memory is None  # no prior memory in test DB


async def test_collect_tm_unavailable_raises_upstream(mongo_db):
    collector = make_collector(
        mongo_db,
        tm_side_effect=UpstreamError("TM unreachable"),
    )
    with pytest.raises(UpstreamError):
        await collector.collect("T-001", "proj-1")


async def test_collect_empty_audit_trail_proceeds(mongo_db):
    collector = make_collector(mongo_db, events=[])
    ctx = await collector.collect("T-001", "proj-1")
    assert ctx.audit_trail == []


async def test_collect_includes_existing_memory(mongo_db):
    # Seed memory in Mongo
    await mongo_db.project_memory.insert_one({
        "_id": "proj-1",
        "content": "project_id: proj-1",
        "version": 1,
        "last_ticket_id": "T-000",
        "updated_at": "2026-06-20T09:00:00Z",
    })
    collector = make_collector(mongo_db)
    ctx = await collector.collect("T-001", "proj-1")
    assert ctx.current_memory == "project_id: proj-1"


async def test_collect_adr_refs_included(mongo_db):
    await mongo_db.adrs.insert_one({
        "_id": "ADR-001",
        "project_id": "proj-1",
        "title": "Use PG",
        "status": "accepted",
        "summary": "PG for queue",
        "content": "...",
        "ticket_id": "T-000",
        "created_at": "2026-06-20T09:00:00Z",
        "updated_at": "2026-06-20T09:00:00Z",
    })
    collector = make_collector(mongo_db)
    ctx = await collector.collect("T-001", "proj-1")
    assert len(ctx.adr_refs) == 1
    assert ctx.adr_refs[0]["id"] == "ADR-001"
