"""Shared pytest fixtures for Agent Tools tests."""

import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import git
import pytest
import respx
from jose import jwt
from src.config import Settings

_TEST_JWT_SECRET = "test-secret-do-not-use-in-production"


@pytest.fixture
def tmp_git_repo():
    """Real git.Repo in a temp directory with two commits and known content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = git.Repo.init(tmpdir)
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()

        readme = Path(tmpdir) / "README.md"
        readme.write_text("# Test Repo\nThis is a test repository.\n")

        src_dir = Path(tmpdir) / "src"
        src_dir.mkdir()
        py_file = src_dir / "main.py"
        py_file.write_text(
            "def hello():\n    return 'hello world'\n\ndef authenticate(user):\n    return True\n"
        )

        repo.index.add(["README.md", "src/main.py"])
        repo.index.commit("Initial commit")

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
        test_jwt_secret=_TEST_JWT_SECRET,
        auth_mode="local",
    )


@pytest.fixture
def mock_distiller():
    """respx router that intercepts all requests to DISTILLER_BASE_URL."""
    with respx.mock(base_url="http://context-distiller:8001", assert_all_called=False) as router:
        yield router


# ---------------------------------------------------------------------------
# Auth fixtures (Keycloak-shaped HS256 tokens for AUTH_MODE=local)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def set_auth_mode(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", _TEST_JWT_SECRET)
    from src import config as cfg

    cfg.get_settings.cache_clear()
    yield
    cfg.get_settings.cache_clear()


def _make_token(sub: str, email: str, roles: list[str]) -> str:
    payload = {
        "sub": sub,
        "email": email,
        "preferred_username": email,
        "realm_access": {"roles": roles},
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, _TEST_JWT_SECRET, algorithm="HS256")


@pytest.fixture
def user_token() -> str:
    return _make_token("user-sub-001", "user@test.local", ["user"])


@pytest.fixture
def admin_token() -> str:
    return _make_token("admin-sub-001", "admin@test.local", ["user", "administrator"])


@pytest.fixture
def auth_headers(user_token) -> dict:
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}
