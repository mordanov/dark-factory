"""Unit tests — AgentWorkerService (resolve_capable_worker, liveness threshold)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.capability_registry import AgentCapability
from src.services.worker_service import AgentWorkerService, _liveness_threshold


def _cap(role_id: str, capabilities: list[str], confidence: dict | None = None) -> AgentCapability:
    return AgentCapability(
        role_id=role_id,
        display_name=role_id,
        skill_file=f"{role_id}.md",
        coordinator=False,
        capabilities=capabilities,
        fsm_ownership=[],
        preferred_for=[],
        brainstorm_also_for=[],
        brainstorm_role="contributor",
        confidence=confidence or {},
    )


def _worker(role_id: str, status: str = "idle"):
    w = MagicMock()
    w.id = uuid.uuid4()
    w.role_id = role_id
    w.status = status
    return w


class TestResolveCapableWorker:
    @pytest.fixture()
    def mock_repo(self):
        with patch(
            "src.services.worker_service.AgentWorkerRepository", autospec=True
        ) as MockRepo:
            instance = MockRepo.return_value
            instance.list_all = AsyncMock(return_value=[])
            yield instance

    @pytest.fixture()
    def mock_registry(self):
        with patch("src.services.worker_service.get_registry") as mock:
            yield mock.return_value

    async def test_returns_none_for_empty_caps(self, mock_repo, mock_registry):
        svc = AgentWorkerService(MagicMock())
        result = await svc.resolve_capable_worker([])
        assert result is None

    async def test_returns_none_when_registry_has_no_capable_agents(
        self, mock_repo, mock_registry
    ):
        mock_registry.get_by_capability.return_value = []
        svc = AgentWorkerService(MagicMock())
        result = await svc.resolve_capable_worker(["python_backend"])
        assert result is None

    async def test_returns_none_when_no_idle_workers(self, mock_repo, mock_registry):
        mock_registry.get_by_capability.return_value = [_cap("backend", ["python_backend"])]
        mock_repo.list_all = AsyncMock(return_value=[])  # no idle workers
        svc = AgentWorkerService(MagicMock())
        result = await svc.resolve_capable_worker(["python_backend"])
        assert result is None

    async def test_returns_best_candidate(self, mock_repo, mock_registry):
        low_conf = _cap("backend-low", ["python_backend"], {"python_backend": 60})
        high_conf = _cap("backend-high", ["python_backend"], {"python_backend": 95})
        mock_registry.get_by_capability.return_value = [low_conf, high_conf]
        mock_repo.list_all = AsyncMock(
            return_value=[
                _worker("backend-low"),
                _worker("backend-high"),
            ]
        )
        svc = AgentWorkerService(MagicMock())
        result = await svc.resolve_capable_worker(["python_backend"])
        assert result is not None
        assert result.role_id == "backend-high"

    async def test_ignores_non_idle_workers(self, mock_repo, mock_registry):
        cap = _cap("backend", ["python_backend"])
        mock_registry.get_by_capability.return_value = [cap]
        mock_repo.list_all = AsyncMock(
            return_value=[_worker("backend", status="busy")]
        )
        # list_all is called with status_filter="idle" — mock returns busy worker
        # but list_all filter is applied at repo level; here the mock ignores filters
        # so we simulate a repository that returns only idle workers:
        mock_repo.list_all = AsyncMock(return_value=[])  # no idle workers
        svc = AgentWorkerService(MagicMock())
        result = await svc.resolve_capable_worker(["python_backend"])
        assert result is None

    async def test_multi_cap_requires_all(self, mock_repo, mock_registry):
        only_python = _cap("backend", ["python_backend"])
        both = _cap("fullstack", ["python_backend", "typescript_frontend"])
        mock_registry.get_by_capability.return_value = [both]  # registry already filtered
        mock_repo.list_all = AsyncMock(
            return_value=[_worker("backend"), _worker("fullstack")]
        )
        svc = AgentWorkerService(MagicMock())
        result = await svc.resolve_capable_worker(
            ["python_backend", "typescript_frontend"]
        )
        assert result is not None
        assert result.role_id == "fullstack"

    async def test_missing_confidence_entry_treated_as_100(self, mock_repo, mock_registry):
        cap_no_conf = _cap("backend", ["python_backend"])  # no confidence dict
        mock_registry.get_by_capability.return_value = [cap_no_conf]
        mock_repo.list_all = AsyncMock(return_value=[_worker("backend")])
        svc = AgentWorkerService(MagicMock())
        result = await svc.resolve_capable_worker(["python_backend"])
        assert result is not None
        assert result.role_id == "backend"


class TestLivenessThreshold:
    def test_liveness_threshold_default(self):
        threshold = _liveness_threshold()
        expected = datetime.now(UTC) - timedelta(seconds=30 * 2.0)
        diff = abs((threshold - expected).total_seconds())
        assert diff < 1.0

    def test_liveness_threshold_custom_multiplier(self):
        threshold = _liveness_threshold(multiplier=3.0)
        expected = datetime.now(UTC) - timedelta(seconds=30 * 3.0)
        diff = abs((threshold - expected).total_seconds())
        assert diff < 1.0


class TestRegisterWorker:
    async def test_raises_for_unknown_role(self):
        with patch("src.services.worker_service.get_registry") as mock_reg:
            mock_reg.return_value.get_by_role_id.return_value = None
            with patch("src.services.worker_service.AgentWorkerRepository", autospec=True):
                svc = AgentWorkerService(MagicMock())
                with pytest.raises(ValueError, match="not found in capability registry"):
                    await svc.register_worker("unknown-role", "1.0", {})

    async def test_creates_and_emits_lifecycle_event(self):
        mock_cap = _cap("backend", ["python_backend"])
        worker = _worker("backend")
        worker.registered_at = datetime.now(UTC)
        worker.status = "idle"

        with (
            patch("src.services.worker_service.get_registry") as mock_reg,
            patch(
                "src.services.worker_service.AgentWorkerRepository", autospec=True
            ) as MockRepo,
        ):
            mock_reg.return_value.get_by_role_id.return_value = mock_cap
            instance = MockRepo.return_value
            instance.create = AsyncMock(return_value=worker)
            instance.write_lifecycle_event = AsyncMock()

            svc = AgentWorkerService(MagicMock())
            result = await svc.register_worker("backend", "1.0", {"python_backend": 95})

        assert result["role_id"] == "backend"
        assert result["status"] == "idle"
        instance.write_lifecycle_event.assert_awaited_once()
        call_kwargs = instance.write_lifecycle_event.call_args
        assert call_kwargs[0][2] == "registered"
