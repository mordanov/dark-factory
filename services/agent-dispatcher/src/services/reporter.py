"""Reporter — posts TM comments and triggers Orchestrator evaluation."""

from __future__ import annotations

import httpx
import structlog

from src.core.config import get_settings
from src.core.exceptions import OrchestratorError
from src.core.keycloak_client import get_kc_client
from src.schemas.schemas import AgentResult

logger = structlog.get_logger(__name__)


class Reporter:
    async def report_result(
        self,
        ticket_id: str,
        project_id: str,
        result: AgentResult,
    ) -> None:
        settings = get_settings()
        headers = {**await get_kc_client().async_auth_headers(), "Content-Type": "application/json"}

        await self._post_tm_comment(
            settings.ticket_manager_base_url,
            project_id,
            ticket_id,
            result.tm_comment or result.summary,
            headers,
        )

        await self._trigger_orchestrator(
            settings.orchestrator_base_url,
            ticket_id,
            project_id,
            headers,
        )

    async def _post_tm_comment(
        self,
        tm_url: str,
        project_id: str,
        ticket_id: str,
        content: str,
        headers: dict,
    ) -> None:
        url = f"{tm_url}/api/projects/{project_id}/tickets/{ticket_id}/comments"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json={"content": content}, headers=headers)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Failed to post TM comment", ticket_id=ticket_id, error=str(exc))

    async def _trigger_orchestrator(
        self,
        orch_url: str,
        ticket_id: str,
        project_id: str,
        headers: dict,
    ) -> None:
        url = f"{orch_url}/api/v1/jobs/trigger"
        payload = {"ticket_id": ticket_id, "project_id": project_id}

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                return
            except Exception as exc:
                if attempt == 1:
                    raise OrchestratorError(f"Orchestrator trigger failed: {exc}") from exc
                logger.warning(
                    "Orchestrator trigger attempt failed, retrying",
                    ticket_id=ticket_id,
                    attempt=attempt,
                    error=str(exc),
                )
