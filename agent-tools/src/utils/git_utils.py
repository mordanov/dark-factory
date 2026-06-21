import os
from pathlib import Path

import git


# Extension → language name
_EXT_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".md": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".sh": "shell",
    ".bash": "shell",
    ".html": "html",
    ".css": "css",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".sql": "sql",
    ".tf": "terraform",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".xml": "xml",
    ".dockerfile": "dockerfile",
}

_DOCKERFILE_NAMES = {"dockerfile", "dockerfile.dev", "dockerfile.prod"}


def language_from_ext(filename: str) -> str:
    name = os.path.basename(filename).lower()
    if name in _DOCKERFILE_NAMES:
        return "dockerfile"
    ext = Path(filename).suffix.lower()
    return _EXT_MAP.get(ext, "unknown")


def open_repo(path: str) -> git.Repo:
    try:
        return git.Repo(path)
    except (git.InvalidGitRepositoryError, git.NoSuchPathError) as exc:
        raise _RepoNotConfiguredError(str(exc)) from exc


def validate_path(path: str, repo_root: str) -> str:
    """Normalise path and ensure it stays within repo_root. Returns clean relative path."""
    # Strip leading slashes so Path doesn't treat it as absolute
    clean = path.lstrip("/")
    resolved = (Path(repo_root) / clean).resolve()
    root_resolved = Path(repo_root).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise _InvalidInputError(f"Path '{path}' traverses outside the repository root")
    return str(resolved.relative_to(root_resolved))


class _RepoNotConfiguredError(Exception):
    pass


class _InvalidInputError(Exception):
    pass


# Re-export for use in tools
RepoNotConfiguredError = _RepoNotConfiguredError
InvalidInputError = _InvalidInputError
