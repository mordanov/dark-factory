import httpx
import pytest
import respx
from src.config import Settings
from src.tools.document_store import fetch_project_memory

_BASE = "http://context-distiller:8001"


@pytest.fixture
def settings(tmp_git_repo):
    _, tmpdir = tmp_git_repo
    return Settings(
        git_repo_path=tmpdir,
        jwt_secret_key="test-secret",
        distiller_base_url=_BASE,
    )


async def test_fetch_memory_happy_path(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": "project: test\nkey: value\n",
                    "last_ticket_id": "T-42",
                    "version": 1,
                },
            )
        )
        result = await fetch_project_memory("proj-1", settings=settings)
    assert result.success is True
    assert "project: test" in result.result["memory"]
    assert result.result["source_ticket_ids"] == ["T-42"]


async def test_fetch_memory_not_found(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/no-proj").mock(return_value=httpx.Response(404))
        result = await fetch_project_memory("no-proj", settings=settings)
    assert result.success is False
    assert result.error.code == "MEMORY_NOT_FOUND"
    assert result.error.retryable is False


async def test_fetch_memory_distiller_unavailable(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-x").mock(side_effect=httpx.ConnectError("refused"))
        result = await fetch_project_memory("proj-x", settings=settings)
    assert result.success is False
    assert result.error.code == "DISTILLER_UNAVAILABLE"
    assert result.error.retryable is True


async def test_fetch_memory_timeout(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-t").mock(side_effect=httpx.TimeoutException("timeout"))
        result = await fetch_project_memory("proj-t", settings=settings)
    assert result.success is False
    assert result.error.code == "TIMEOUT"
    assert result.error.retryable is True


async def test_fetch_memory_truncation(settings):
    long_content = "x" * 10000
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-big").mock(
            return_value=httpx.Response(
                200,
                json={"content": long_content, "last_ticket_id": "", "version": 1},
            )
        )
        result = await fetch_project_memory("proj-big", max_tokens=100, settings=settings)
    assert result.success is True
    memory = result.result["memory"]
    assert len(memory) <= 100 * 4 + len("\n# [TRUNCATED]")
    assert memory.endswith("# [TRUNCATED]")


async def test_fetch_memory_empty_ticket_id(settings):
    with respx.mock(base_url=_BASE) as mock:
        mock.get("/api/v1/memory/proj-empty").mock(
            return_value=httpx.Response(
                200,
                json={"content": "data: yes\n", "last_ticket_id": "", "version": 1},
            )
        )
        result = await fetch_project_memory("proj-empty", settings=settings)
    assert result.success is True
    assert result.result["source_ticket_ids"] == []
