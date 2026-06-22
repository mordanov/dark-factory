import asyncio
from unittest.mock import patch

import pytest
from src.config import Settings
from src.tools.git_read import search_code


@pytest.fixture
def settings(test_settings):
    return test_settings


async def test_search_code_happy_path(settings):
    result = await search_code("hello world", settings=settings)
    assert result.success is True
    matches = result.result["matches"]
    assert len(matches) >= 1
    m = matches[0]
    assert "main.py" in m["file"]
    assert m["line"] > 0
    assert "hello world" in m["content"].lower()


async def test_search_code_case_insensitive(settings):
    result = await search_code("HELLO WORLD", case_sensitive=False, settings=settings)
    assert result.success is True
    assert len(result.result["matches"]) >= 1


async def test_search_code_case_sensitive_no_match(settings):
    result = await search_code("HELLO WORLD", case_sensitive=True, settings=settings)
    assert result.success is True
    assert result.result["matches"] == []


async def test_search_code_path_filter(settings):
    result = await search_code("hello", path_filter="src/*.py", settings=settings)
    assert result.success is True
    for m in result.result["matches"]:
        assert m["file"].startswith("src/")


async def test_search_code_no_results(settings):
    result = await search_code("xyzzy_nonexistent_string_12345", settings=settings)
    assert result.success is True
    assert result.result["matches"] == []
    assert result.result["truncated"] is False


async def test_search_code_empty_query(settings):
    result = await search_code("", settings=settings)
    assert result.success is False
    assert result.error.code == "INVALID_INPUT"


async def test_search_code_truncation(settings, tmp_git_repo):
    from pathlib import Path

    import git as gitlib

    _, tmpdir = tmp_git_repo
    repo = gitlib.Repo(tmpdir)
    # Add a file with many matching lines
    big = Path(tmpdir) / "big.txt"
    big.write_text("\n".join(f"match line {i}" for i in range(60)))
    repo.index.add(["big.txt"])
    repo.index.commit("Add big file")

    result = await search_code("match line", max_results=50, settings=settings)
    assert result.success is True
    assert len(result.result["matches"]) == 50
    assert result.result["truncated"] is True


async def test_search_code_timeout(settings):
    async def slow(*a, **kw):
        await asyncio.sleep(100)

    with patch("src.tools.git_read.asyncio.to_thread", new=slow):
        result = await search_code("hello", settings=settings)
    assert result.success is False
    assert result.error.code == "SEARCH_TIMEOUT"
    assert result.error.retryable is True


async def test_search_code_repo_not_configured():
    bad = Settings(git_repo_path="/no/such/path", jwt_secret_key="s")
    result = await search_code("hello", settings=bad)
    assert result.success is False
    assert result.error.code == "REPO_NOT_CONFIGURED"
