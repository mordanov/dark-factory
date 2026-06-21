import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings
from src.tools.git_read import read_file


@pytest.fixture
def settings(test_settings):
    return test_settings


async def test_read_file_happy_path(settings, tmp_git_repo):
    _, tmpdir = tmp_git_repo
    result = await read_file("README.md", ref="main", settings=settings)
    assert result.success is True
    assert "Test Repo" in result.result["content"]
    assert result.result["size_bytes"] > 0
    assert result.result["language"] == "markdown"
    assert result.tool == "read_file"


async def test_read_file_python_language(settings, tmp_git_repo):
    result = await read_file("src/main.py", ref="main", settings=settings)
    assert result.success is True
    assert result.result["language"] == "python"


async def test_read_file_not_found(settings):
    result = await read_file("nonexistent.txt", ref="main", settings=settings)
    assert result.success is False
    assert result.error.code == "FILE_NOT_FOUND"
    assert result.error.retryable is False


async def test_read_file_ref_not_found(settings):
    result = await read_file("README.md", ref="nonexistent-branch-xyz", settings=settings)
    assert result.success is False
    assert result.error.code == "REF_NOT_FOUND"
    assert result.error.retryable is False


async def test_read_file_path_traversal(settings):
    result = await read_file("../etc/passwd", ref="main", settings=settings)
    assert result.success is False
    assert result.error.code == "INVALID_INPUT"
    assert result.error.retryable is False


async def test_read_file_repo_not_configured():
    bad_settings = Settings(git_repo_path="/nonexistent/path", jwt_secret_key="s")
    result = await read_file("README.md", ref="main", settings=bad_settings)
    assert result.success is False
    assert result.error.code == "REPO_NOT_CONFIGURED"
    assert result.error.retryable is False


async def test_read_file_timeout(settings, tmp_git_repo):
    async def slow(*args, **kwargs):
        await asyncio.sleep(100)

    with patch("src.tools.git_read.asyncio.to_thread", new=slow):
        result = await read_file("README.md", ref="main", settings=settings)
    assert result.success is False
    assert result.error.code == "TIMEOUT"
    assert result.error.retryable is True
