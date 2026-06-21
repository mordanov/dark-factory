import asyncio
from unittest.mock import patch

import git as gitlib
import pytest
from pathlib import Path

from src.config import Settings
from src.tools.git_read import get_diff


@pytest.fixture
def settings(test_settings):
    return test_settings


async def test_get_diff_happy_path(settings, tmp_git_repo):
    repo, tmpdir = tmp_git_repo
    commits = list(repo.iter_commits("main"))
    # commits[0] = latest, commits[-1] = first
    base = commits[-1].hexsha
    head = commits[0].hexsha

    result = await get_diff(base, head, settings=settings)
    assert result.success is True
    assert len(result.result["diff"]) > 0
    assert len(result.result["files_changed"]) > 0
    assert result.result["stats"]["additions"] >= 0


async def test_get_diff_empty_same_refs(settings, tmp_git_repo):
    repo, _ = tmp_git_repo
    sha = repo.head.commit.hexsha
    result = await get_diff(sha, sha, settings=settings)
    assert result.success is True
    assert result.result["diff"] == ""
    assert result.result["files_changed"] == []
    assert result.result["stats"]["additions"] == 0


async def test_get_diff_ref_not_found_base(settings):
    result = await get_diff("nonexistent-base-xyz", "main", settings=settings)
    assert result.success is False
    assert result.error.code == "REF_NOT_FOUND"


async def test_get_diff_ref_not_found_head(settings):
    result = await get_diff("main", "nonexistent-head-xyz", settings=settings)
    assert result.success is False
    assert result.error.code == "REF_NOT_FOUND"


async def test_get_diff_path_filter(settings, tmp_git_repo):
    repo, tmpdir = tmp_git_repo
    commits = list(repo.iter_commits("main"))
    base = commits[-1].hexsha
    head = commits[0].hexsha

    result = await get_diff(base, head, path_filter="*.md", settings=settings)
    assert result.success is True
    # No .md files changed between commits
    assert result.result["files_changed"] == [] or all(
        f.endswith(".md") for f in result.result["files_changed"]
    )


async def test_get_diff_timeout(settings):
    async def slow(*a, **kw):
        await asyncio.sleep(100)

    with patch("src.tools.git_read.asyncio.to_thread", new=slow):
        result = await get_diff("main", "main", settings=settings)
    assert result.success is False
    assert result.error.code == "TIMEOUT"
    assert result.error.retryable is True
