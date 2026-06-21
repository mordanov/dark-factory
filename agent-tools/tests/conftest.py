import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import git
import pytest
import respx

from src.config import Settings


@pytest.fixture
def tmp_git_repo():
    """Real git.Repo in a temp directory with two commits and known content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = git.Repo.init(tmpdir)
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()

        # First commit: README + Python file
        readme = Path(tmpdir) / "README.md"
        readme.write_text("# Test Repo\nThis is a test repository.\n")

        src_dir = Path(tmpdir) / "src"
        src_dir.mkdir()
        py_file = src_dir / "main.py"
        py_file.write_text("def hello():\n    return 'hello world'\n\ndef authenticate(user):\n    return True\n")

        repo.index.add(["README.md", "src/main.py"])
        repo.index.commit("Initial commit")

        # Second commit: add another file
        utils_file = src_dir / "utils.py"
        utils_file.write_text("def helper():\n    pass\n")
        repo.index.add(["src/utils.py"])
        repo.index.commit("Add utils")

        yield repo, tmpdir


@pytest.fixture
def test_settings(tmp_git_repo):
    """Settings pointing at the temp git repo."""
    _, tmpdir = tmp_git_repo
    return Settings(
        git_repo_path=tmpdir,
        jwt_secret_key="test-secret",
    )


@pytest.fixture
def mock_distiller():
    """respx router that intercepts all requests to DISTILLER_BASE_URL."""
    with respx.mock(base_url="http://context-distiller:8001", assert_all_called=False) as router:
        yield router
