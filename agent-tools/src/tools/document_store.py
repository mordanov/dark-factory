"""Phase 2 Document Store tools: fetch_project_memory, fetch_adrs."""
import time

import httpx

from src.config import Settings, get_settings
from src.schemas import AdrSummary, FetchAdrsResult, FetchProjectMemoryResult, ToolEnvelope
from src.utils.auth import make_service_jwt
from src.utils.envelope import build_error, build_success

_TOOL_MEMORY = "fetch_project_memory"
_TOOL_ADRS = "fetch_adrs"

_TRUNCATION_MARKER = "\n# [TRUNCATED]"


# ---------------------------------------------------------------------------
# fetch_project_memory
# ---------------------------------------------------------------------------

async def fetch_project_memory(
    project_id: str,
    ticket_id: str = "",
    max_tokens: int = 2000,
    settings: Settings | None = None,
) -> ToolEnvelope:
    t0 = time.monotonic()
    s = settings or get_settings()
    tool = _TOOL_MEMORY

    token = make_service_jwt(s)
    url = f"{s.distiller_base_url}/api/v1/memory/{project_id}"

    try:
        async with httpx.AsyncClient(timeout=s.distiller_timeout_seconds) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    except httpx.TimeoutException:
        return build_error(tool, "TIMEOUT", "Context Distiller request timed out", True, t0)
    except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.TransportError) as exc:
        return build_error(tool, "DISTILLER_UNAVAILABLE", str(exc), True, t0)

    if resp.status_code == 404:
        return build_error(tool, "MEMORY_NOT_FOUND", f"No memory found for project '{project_id}'", False, t0)
    if resp.status_code == 401 or resp.status_code == 403:
        return build_error(tool, "AUTH_FAILED", "Authentication failed", False, t0)
    if not resp.is_success:
        return build_error(tool, "DISTILLER_UNAVAILABLE", f"Unexpected status {resp.status_code}", True, t0)

    data = resp.json()
    memory: str = data.get("content", "")
    last_ticket_id: str = data.get("last_ticket_id", "")

    char_budget = max_tokens * 4
    if len(memory) > char_budget:
        memory = memory[:char_budget] + _TRUNCATION_MARKER

    source_ticket_ids = [last_ticket_id] if last_ticket_id else []

    result = FetchProjectMemoryResult(memory=memory, source_ticket_ids=source_ticket_ids)
    return build_success(tool, result.model_dump(), t0)


# ---------------------------------------------------------------------------
# fetch_adrs
# ---------------------------------------------------------------------------

async def fetch_adrs(
    project_id: str,
    status_filter: str = "accepted",
    domain_filter: str = "",
    settings: Settings | None = None,
) -> ToolEnvelope:
    t0 = time.monotonic()
    s = settings or get_settings()
    tool = _TOOL_ADRS

    token = make_service_jwt(s)

    # "all" → omit status query param, otherwise pass it
    params: dict[str, str] = {}
    if status_filter != "all":
        params["status"] = status_filter

    url = f"{s.distiller_base_url}/api/v1/memory/{project_id}/adrs"

    try:
        async with httpx.AsyncClient(timeout=s.distiller_timeout_seconds) as client:
            resp = await client.get(url, params=params, headers={"Authorization": f"Bearer {token}"})
    except httpx.TimeoutException:
        return build_error(tool, "TIMEOUT", "Context Distiller request timed out", True, t0)
    except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.TransportError) as exc:
        return build_error(tool, "DISTILLER_UNAVAILABLE", str(exc), True, t0)

    if resp.status_code == 401 or resp.status_code == 403:
        return build_error(tool, "AUTH_FAILED", "Authentication failed", False, t0)
    if not resp.is_success:
        return build_error(tool, "DISTILLER_UNAVAILABLE", f"Unexpected status {resp.status_code}", True, t0)

    data = resp.json()
    raw_adrs = data.get("adrs", [])

    adrs: list[AdrSummary] = []
    for a in raw_adrs:
        title = a.get("title", "")
        summary = a.get("summary", "")
        # Client-side domain filter: substring match on title + summary
        if domain_filter and domain_filter.lower() not in (title + " " + summary).lower():
            continue
        # Map created_at → date (take date portion of ISO string)
        created_at: str = a.get("created_at", "")
        date_str = created_at[:10] if created_at else ""
        adrs.append(AdrSummary(
            id=a.get("id", ""),
            title=title,
            status=a.get("status", ""),
            summary=summary,
            date=date_str,
        ))

    result = FetchAdrsResult(adrs=adrs)
    return build_success(tool, result.model_dump(), t0)
