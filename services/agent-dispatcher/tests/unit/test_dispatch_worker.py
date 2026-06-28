"""Unit tests for DispatchWorker."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


async def test_worker_start_and_stop():
    with (
        patch("src.workers.dispatch_worker.get_settings") as mock_settings,
        patch("src.workers.dispatch_worker.AsyncSessionLocal"),
    ):
        settings = MagicMock()
        settings.worker_max_concurrent_runs = 2
        settings.poll_interval_seconds = 0.05
        mock_settings.return_value = settings

        from src.workers.dispatch_worker import DispatchWorker

        worker = DispatchWorker()

        with patch.object(worker, "_poll_loop", new=AsyncMock()):
            await worker.start()
            assert worker._running is True
            await worker.stop()
            assert worker._running is False


async def test_worker_stop_cancels_loop_task():
    with (
        patch("src.workers.dispatch_worker.get_settings") as mock_settings,
        patch("src.workers.dispatch_worker.AsyncSessionLocal"),
    ):
        settings = MagicMock()
        settings.worker_max_concurrent_runs = 2
        settings.poll_interval_seconds = 0.05
        mock_settings.return_value = settings

        from src.workers.dispatch_worker import DispatchWorker

        worker = DispatchWorker()

        async def hang():
            await asyncio.sleep(9999)

        with patch.object(worker, "_poll_loop", side_effect=hang):
            await worker.start()
            await asyncio.sleep(0.02)
            await worker.stop()
            assert not worker._running


async def test_run_with_semaphore_calls_process_ticket():
    with (
        patch("src.workers.dispatch_worker.get_settings") as mock_settings,
        patch("src.workers.dispatch_worker.AsyncSessionLocal") as mock_session_cls,
    ):
        settings = MagicMock()
        settings.worker_max_concurrent_runs = 2
        settings.poll_interval_seconds = 0.05
        mock_settings.return_value = settings

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_db

        mock_ticket = MagicMock(id="TKT-W-001")

        from src.workers.dispatch_worker import DispatchWorker

        worker = DispatchWorker()

        mock_pt = AsyncMock()
        with patch("src.services.dispatcher_service.process_ticket", mock_pt):
            await worker._run_with_semaphore(mock_ticket)
            mock_pt.assert_called_once_with(
                mock_ticket, mock_db, required_capabilities=mock_ticket.required_capabilities
            )


async def test_run_with_semaphore_swallows_exception():
    with (
        patch("src.workers.dispatch_worker.get_settings") as mock_settings,
        patch("src.workers.dispatch_worker.AsyncSessionLocal") as mock_session_cls,
    ):
        settings = MagicMock()
        settings.worker_max_concurrent_runs = 2
        settings.poll_interval_seconds = 0.05
        mock_settings.return_value = settings

        mock_db = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_db

        mock_ticket = MagicMock(id="TKT-W-002")

        from src.workers.dispatch_worker import DispatchWorker

        worker = DispatchWorker()

        with patch(
            "src.services.dispatcher_service.process_ticket",
            new=AsyncMock(side_effect=Exception("boom")),
        ):
            # Should not raise
            await worker._run_with_semaphore(mock_ticket)
