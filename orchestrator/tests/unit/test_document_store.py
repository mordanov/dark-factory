"""Unit tests for DocumentStore using mongomock-motor."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.document_store.store import (
    DocumentStore, _extract_adr_title, _extract_adr_section
)


# ---------------------------------------------------------------------------
# Helper parsing
# ---------------------------------------------------------------------------

def test_extract_adr_title():
    md = "# ADR-003: Use PostgreSQL\n\nsome content"
    assert _extract_adr_title(md) == "Use PostgreSQL"


def test_extract_adr_title_missing():
    assert _extract_adr_title("no title here") is None


def test_extract_adr_section():
    md = "## Decision\nWe chose PostgreSQL.\n## Consequences\nFoo"
    result = _extract_adr_section(md, "Decision")
    assert "PostgreSQL" in result


def test_extract_adr_section_missing():
    assert _extract_adr_section("no sections", "Decision") is None


# ---------------------------------------------------------------------------
# DocumentStore with mocked Mongo
# ---------------------------------------------------------------------------

def make_store():
    db = MagicMock()
    return DocumentStore(db), db


@pytest.mark.asyncio
async def test_get_memory_none_when_missing():
    store, db = make_store()
    db.__getitem__.return_value.find_one = AsyncMock(return_value=None)
    result = await store.get_memory("proj-1")
    assert result is None


@pytest.mark.asyncio
async def test_get_memory_returns_response():
    store, db = make_store()
    doc = {"_id": "proj-1", "content": "yaml: content", "version": 3,
           "last_ticket_id": "t-5", "updated_at": None}
    db.__getitem__.return_value.find_one = AsyncMock(return_value=doc)
    result = await store.get_memory("proj-1")
    assert result.content == "yaml: content"
    assert result.version == 3


@pytest.mark.asyncio
async def test_save_memory_increments_version():
    store, db = make_store()
    existing = {"_id": "proj-1", "content": "old", "version": 5,
                "last_ticket_id": "t-4", "updated_at": None}
    col = MagicMock()
    col.find_one = AsyncMock(return_value=existing)
    col.insert_one = AsyncMock()
    col.replace_one = AsyncMock()
    col.count_documents = AsyncMock(return_value=3)
    col.find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(return_value=[])
    col.delete_many = AsyncMock()
    db.__getitem__.return_value = col

    result = await store.save_memory("proj-1", "new content", "t-5")
    assert result.version == 6
    assert result.content == "new content"


@pytest.mark.asyncio
async def test_next_adr_number_first():
    store, db = make_store()
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    db.__getitem__.return_value = col
    n = await store.next_adr_number("proj-1")
    assert n == 1


@pytest.mark.asyncio
async def test_next_adr_number_increments():
    store, db = make_store()
    col = MagicMock()
    col.find_one = AsyncMock(return_value={"adr_number": 7})
    db.__getitem__.return_value = col
    n = await store.next_adr_number("proj-1")
    assert n == 8


@pytest.mark.asyncio
async def test_save_adr_returns_id():
    store, db = make_store()
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)   # next_adr_number → 1
    col.insert_one = AsyncMock()
    db.__getitem__.return_value = col

    adr_md = "# ADR-001: Use Postgres\n\n## Decision\nPostgres is chosen.\n## Consequences\n### Positive\n- fast"
    adr_id = await store.save_adr("proj-1", adr_md, "t-1")
    assert adr_id == "ADR-001"
