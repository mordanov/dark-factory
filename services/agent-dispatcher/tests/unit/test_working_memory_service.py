"""Unit tests — WorkingMemoryService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.services.working_memory_service import WorkingMemoryService


def _svc_with_repo(repo_mock):
    db = MagicMock()
    with patch(
        "src.services.working_memory_service.WorkingMemoryRepository",
        return_value=repo_mock,
    ):
        return WorkingMemoryService(db)


def _mock_repo():
    repo = MagicMock()
    repo.append = AsyncMock()
    repo.list_for_ticket = AsyncMock(return_value=[])
    repo.get_run_ticket = AsyncMock(return_value=None)
    repo.delete_expired = AsyncMock(return_value=0)
    return repo


class TestAppend:
    async def test_delegates_to_repo(self):
        repo = _mock_repo()
        fake_entry = MagicMock()
        fake_entry.ticket_id = "TICKET-1"
        fake_entry.entry_type = "observation"
        repo.append = AsyncMock(return_value=fake_entry)

        svc = _svc_with_repo(repo)
        result = await svc.append(
            ticket_id="TICKET-1",
            run_id=uuid.uuid4(),
            author_role_id="sa",
            entry_type="observation",
            content="Some observation",
            tags=["arch"],
        )

        repo.append.assert_awaited_once()
        assert result is fake_entry

    async def test_propagates_value_error_from_repo(self):
        repo = _mock_repo()
        repo.append = AsyncMock(side_effect=ValueError("content exceeds maximum length"))

        svc = _svc_with_repo(repo)
        with pytest.raises(ValueError, match="maximum length"):
            await svc.append(
                ticket_id="TICKET-1",
                run_id=uuid.uuid4(),
                author_role_id="sa",
                entry_type="observation",
                content="x" * 65_537,
            )


class TestListForTicket:
    async def test_no_run_id_no_isolation_check(self):
        repo = _mock_repo()
        repo.list_for_ticket = AsyncMock(return_value=["entry1"])

        svc = _svc_with_repo(repo)
        result = await svc.list_for_ticket("TICKET-1")

        repo.get_run_ticket.assert_not_called()
        assert result == ["entry1"]

    async def test_same_ticket_run_id_passes(self):
        repo = _mock_repo()
        run_id = uuid.uuid4()
        repo.get_run_ticket = AsyncMock(return_value="TICKET-1")
        repo.list_for_ticket = AsyncMock(return_value=["entry1"])

        svc = _svc_with_repo(repo)
        result = await svc.list_for_ticket("TICKET-1", requester_run_id=run_id)

        assert result == ["entry1"]

    async def test_unknown_run_id_no_isolation_check(self):
        """If run_id is not in DB (returns None), listing proceeds without error."""
        repo = _mock_repo()
        run_id = uuid.uuid4()
        repo.get_run_ticket = AsyncMock(return_value=None)
        repo.list_for_ticket = AsyncMock(return_value=[])

        svc = _svc_with_repo(repo)
        result = await svc.list_for_ticket("TICKET-1", requester_run_id=run_id)

        assert result == []

    async def test_cross_ticket_run_id_raises_permission_error(self):
        repo = _mock_repo()
        run_id = uuid.uuid4()
        repo.get_run_ticket = AsyncMock(return_value="TICKET-OTHER")

        svc = _svc_with_repo(repo)
        with pytest.raises(PermissionError):
            await svc.list_for_ticket("TICKET-1", requester_run_id=run_id)


class TestCleanupExpired:
    async def test_returns_deleted_count(self):
        repo = _mock_repo()
        repo.delete_expired = AsyncMock(return_value=5)

        svc = _svc_with_repo(repo)
        deleted = await svc.cleanup_expired()

        assert deleted == 5
        repo.delete_expired.assert_awaited_once()

    async def test_returns_zero_when_nothing_to_clean(self):
        repo = _mock_repo()
        repo.delete_expired = AsyncMock(return_value=0)

        svc = _svc_with_repo(repo)
        deleted = await svc.cleanup_expired()

        assert deleted == 0
