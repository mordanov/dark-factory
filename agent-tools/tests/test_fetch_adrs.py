import httpx
import pytest
import respx

from src.config import Settings
from src.tools.document_store import fetch_adrs

_BASE = "http://context-distiller:8001"

_SAMPLE_ADRS = [
    {"id": "adr-1", "title": "Use PostgreSQL for storage", "status": "accepted",
     "summary": "Chose PostgreSQL over MongoDB for relational data", "created_at": "2026-01-10T00:00:00"},
    {"id": "adr-2", "title": "Auth via JWT", "status": "accepted",
     "summary": "Use HS256 JWT for auth service tokens", "created_at": "2026-02-01T00:00:00"},
    {"id": "adr-3", "title": "Use Redis for cache", "status": "proposed",
     "summary": "Considering Redis for session caching", "created_at": "2026-03-05T00:00:00"},
]


@pytest.fixture
def settings(tmp_git_repo):
    _, tmpdir = tmp_git_repo
    return Settings(
        git_repo_path=tmpdir,
        jwt_secret_key="test-secret",
        distiller_base_url=_BASE,
    )


async def test_fetch_adrs_accepted_filter(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-1/adrs").mock(return_value=httpx.Response(
            200, json={"adrs": [a for a in _SAMPLE_ADRS if a["status"] == "accepted"]},
        ))
        result = await fetch_adrs("proj-1", status_filter="accepted", settings=settings)
    assert result.success is True
    assert len(result.result["adrs"]) == 2
    assert all(a["status"] == "accepted" for a in result.result["adrs"])


async def test_fetch_adrs_all_statuses(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-1/adrs").mock(return_value=httpx.Response(
            200, json={"adrs": _SAMPLE_ADRS},
        ))
        result = await fetch_adrs("proj-1", status_filter="all", settings=settings)
    assert result.success is True
    assert len(result.result["adrs"]) == 3


async def test_fetch_adrs_domain_filter(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-1/adrs").mock(return_value=httpx.Response(
            200, json={"adrs": _SAMPLE_ADRS},
        ))
        result = await fetch_adrs("proj-1", status_filter="all", domain_filter="auth", settings=settings)
    assert result.success is True
    adrs = result.result["adrs"]
    assert len(adrs) == 1
    assert adrs[0]["id"] == "adr-2"


async def test_fetch_adrs_empty_list(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-empty/adrs").mock(return_value=httpx.Response(
            200, json={"adrs": []},
        ))
        result = await fetch_adrs("proj-empty", settings=settings)
    assert result.success is True
    assert result.result["adrs"] == []


async def test_fetch_adrs_distiller_unavailable(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-x/adrs").mock(side_effect=httpx.ConnectError("refused"))
        result = await fetch_adrs("proj-x", settings=settings)
    assert result.success is False
    assert result.error.code == "DISTILLER_UNAVAILABLE"
    assert result.error.retryable is True


async def test_fetch_adrs_timeout(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-t/adrs").mock(side_effect=httpx.TimeoutException("timeout"))
        result = await fetch_adrs("proj-t", settings=settings)
    assert result.success is False
    assert result.error.code == "TIMEOUT"
    assert result.error.retryable is True


async def test_fetch_adrs_date_field(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-1/adrs").mock(return_value=httpx.Response(
            200, json={"adrs": [_SAMPLE_ADRS[0]]},
        ))
        result = await fetch_adrs("proj-1", settings=settings)
    assert result.success is True
    assert result.result["adrs"][0]["date"] == "2026-01-10"
