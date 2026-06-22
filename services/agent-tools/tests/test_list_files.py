import pytest
from src.config import Settings
from src.tools.git_read import list_files


@pytest.fixture
def settings(test_settings):
    return test_settings


async def test_list_files_flat(settings):
    result = await list_files(".", recursive=False, settings=settings)
    assert result.success is True
    files = result.result["files"]
    assert "README.md" in files
    # flat: src/ entries should NOT appear (they are in sub-tree)
    assert not any("/" in f for f in files)


async def test_list_files_recursive(settings):
    result = await list_files(".", recursive=True, settings=settings)
    assert result.success is True
    files = result.result["files"]
    assert "src/main.py" in files
    assert "src/utils.py" in files
    assert "README.md" in files


async def test_list_files_pattern(settings):
    result = await list_files(".", recursive=True, pattern="*.py", settings=settings)
    assert result.success is True
    files = result.result["files"]
    assert all(f.endswith(".py") for f in files)
    assert "README.md" not in files
    assert "src/main.py" in files


async def test_list_files_empty_pattern_no_match(settings):
    result = await list_files(".", recursive=True, pattern="*.go", settings=settings)
    assert result.success is True
    assert result.result["files"] == []


async def test_list_files_path_traversal(settings):
    result = await list_files("../etc", settings=settings)
    assert result.success is False
    assert result.error.code == "INVALID_INPUT"


async def test_list_files_not_a_directory(settings):
    result = await list_files("README.md", settings=settings)
    assert result.success is False
    assert result.error.code == "INVALID_INPUT"


async def test_list_files_repo_not_configured():
    bad = Settings(git_repo_path="/no/such/path", jwt_secret_key="s")
    result = await list_files(".", settings=bad)
    assert result.success is False
    assert result.error.code == "REPO_NOT_CONFIGURED"
