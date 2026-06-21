"""Phase 2 git read tools: read_file, list_files, search_code, get_diff."""
import asyncio
import fnmatch
import time
from pathlib import Path

import git

from src.config import Settings, get_settings
from src.schemas import (
    DiffStats,
    GetDiffResult,
    ListFilesResult,
    ReadFileResult,
    SearchCodeResult,
    SearchMatch,
    ToolEnvelope,
)
from src.utils.envelope import build_error, build_success
from src.utils.git_utils import (
    InvalidInputError,
    RepoNotConfiguredError,
    language_from_ext,
    open_repo,
    validate_path,
)

_TOOL_READ_FILE = "read_file"
_TOOL_LIST_FILES = "list_files"
_TOOL_SEARCH_CODE = "search_code"
_TOOL_GET_DIFF = "get_diff"


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

def _read_blob(repo: git.Repo, path: str, ref: str) -> tuple[str, int]:
    """Return (content, size_bytes) — runs in a thread."""
    try:
        commit = repo.commit(ref)
    except git.exc.BadName:
        raise _RefNotFoundError(ref)
    try:
        blob = commit.tree / path
    except KeyError:
        raise _FileNotFoundError(path)
    raw = blob.data_stream.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1", errors="replace")
    return content, len(raw)


async def read_file(
    path: str,
    ref: str = "main",
    settings: Settings | None = None,
) -> ToolEnvelope:
    t0 = time.monotonic()
    s = settings or get_settings()
    tool = _TOOL_READ_FILE

    try:
        repo = open_repo(s.git_repo_path)
        clean_path = validate_path(path, s.git_repo_path)
    except RepoNotConfiguredError as exc:
        return build_error(tool, "REPO_NOT_CONFIGURED", str(exc), False, t0)
    except InvalidInputError as exc:
        return build_error(tool, "INVALID_INPUT", str(exc), False, t0)

    try:
        content, size = await asyncio.wait_for(
            asyncio.to_thread(_read_blob, repo, clean_path, ref),
            timeout=s.git_read_timeout_seconds,
        )
    except asyncio.TimeoutError:
        return build_error(tool, "TIMEOUT", f"read_file timed out after {s.git_read_timeout_seconds}s", True, t0)
    except _RefNotFoundError as exc:
        return build_error(tool, "REF_NOT_FOUND", f"Ref '{exc}' not found", False, t0)
    except _FileNotFoundError as exc:
        return build_error(tool, "FILE_NOT_FOUND", f"Path '{exc}' not found at ref '{ref}'", False, t0)

    result = ReadFileResult(
        content=content,
        size_bytes=size,
        language=language_from_ext(clean_path),
    )
    return build_success(tool, result.model_dump(), t0)


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

def _list_tree(repo: git.Repo, path: str, recursive: bool, pattern: str) -> list[str]:
    """Return sorted relative file paths — runs in a thread."""
    try:
        tree = repo.head.commit.tree
    except ValueError:
        return []

    # Navigate to sub-tree if path is non-root
    if path and path != ".":
        try:
            for part in Path(path).parts:
                tree = tree[part]
        except KeyError:
            raise _FileNotFoundError(path)
        if tree.type != "tree":
            raise InvalidInputError(f"'{path}' is a file, not a directory")

    files: list[str] = []
    _walk_tree(tree, Path(path) if (path and path != ".") else Path(""), recursive, pattern, files)
    return sorted(files)


def _walk_tree(tree: git.Tree, prefix: Path, recursive: bool, pattern: str, out: list[str]) -> None:
    for item in tree:
        item_path = str(prefix / item.name)
        if item.type == "blob":
            if not pattern or fnmatch.fnmatch(item.name, pattern):
                out.append(item_path)
        elif item.type == "tree" and recursive:
            _walk_tree(item, prefix / item.name, recursive, pattern, out)


async def list_files(
    path: str,
    recursive: bool = False,
    pattern: str = "",
    settings: Settings | None = None,
) -> ToolEnvelope:
    t0 = time.monotonic()
    s = settings or get_settings()
    tool = _TOOL_LIST_FILES

    try:
        repo = open_repo(s.git_repo_path)
        clean_path = validate_path(path, s.git_repo_path) if path and path != "." else ""
    except RepoNotConfiguredError as exc:
        return build_error(tool, "REPO_NOT_CONFIGURED", str(exc), False, t0)
    except InvalidInputError as exc:
        return build_error(tool, "INVALID_INPUT", str(exc), False, t0)

    try:
        files = await asyncio.wait_for(
            asyncio.to_thread(_list_tree, repo, clean_path, recursive, pattern),
            timeout=s.git_read_timeout_seconds,
        )
    except asyncio.TimeoutError:
        return build_error(tool, "TIMEOUT", f"list_files timed out after {s.git_read_timeout_seconds}s", True, t0)
    except _FileNotFoundError as exc:
        return build_error(tool, "FILE_NOT_FOUND", f"Path '{exc}' not found", False, t0)
    except InvalidInputError as exc:
        return build_error(tool, "INVALID_INPUT", str(exc), False, t0)

    return build_success(tool, ListFilesResult(files=files).model_dump(), t0)


# ---------------------------------------------------------------------------
# search_code
# ---------------------------------------------------------------------------

def _grep(repo: git.Repo, query: str, path_filter: str, case_sensitive: bool, max_results: int) -> tuple[list[SearchMatch], bool]:
    """Run git grep and parse results — runs in a thread."""
    args = ["--line-number", "--null"]
    if not case_sensitive:
        args.append("--ignore-case")
    args.append(query)
    if path_filter:
        args += ["--", path_filter]

    try:
        raw = repo.git.grep(*args)
    except git.exc.GitCommandError as exc:
        # exit code 1 = no matches (not an error)
        if "exit code(1)" in str(exc) or exc.status == 1:
            return [], False
        raise

    matches: list[SearchMatch] = []
    truncated = False
    # git grep --line-number --null format: filepath\0line_num\0content\n
    for line in raw.splitlines():
        parts = line.split("\0")
        if len(parts) >= 3:
            file_part, lineno_str, content = parts[0], parts[1], "\0".join(parts[2:])
            try:
                matches.append(SearchMatch(
                    file=file_part,
                    line=int(lineno_str),
                    content=content.strip(),
                ))
            except ValueError:
                continue
        if len(matches) >= max_results:
            truncated = True
            break

    return matches, truncated


async def search_code(
    query: str,
    path_filter: str = "",
    case_sensitive: bool = False,
    max_results: int = 50,
    settings: Settings | None = None,
) -> ToolEnvelope:
    t0 = time.monotonic()
    s = settings or get_settings()
    tool = _TOOL_SEARCH_CODE

    if not query or not query.strip():
        return build_error(tool, "INVALID_INPUT", "query must be non-empty", False, t0)

    effective_max = min(max_results, s.search_max_results)

    try:
        repo = open_repo(s.git_repo_path)
    except RepoNotConfiguredError as exc:
        return build_error(tool, "REPO_NOT_CONFIGURED", str(exc), False, t0)

    try:
        matches, truncated = await asyncio.wait_for(
            asyncio.to_thread(_grep, repo, query, path_filter, case_sensitive, effective_max),
            timeout=s.git_read_timeout_seconds,
        )
    except asyncio.TimeoutError:
        return build_error(tool, "SEARCH_TIMEOUT", f"search_code timed out after {s.git_read_timeout_seconds}s", True, t0)

    return build_success(tool, SearchCodeResult(matches=matches, truncated=truncated).model_dump(), t0)


# ---------------------------------------------------------------------------
# get_diff
# ---------------------------------------------------------------------------

def _diff(repo: git.Repo, base_ref: str, head_ref: str, path_filter: str) -> tuple[str, list[str], DiffStats]:
    """Compute diff — runs in a thread."""
    try:
        base_commit = repo.commit(base_ref)
    except git.exc.BadName:
        raise _RefNotFoundError(base_ref)
    try:
        head_commit = repo.commit(head_ref)
    except git.exc.BadName:
        raise _RefNotFoundError(head_ref)

    diff_args: list[str] = ["--unified=3"]
    if path_filter:
        diff_args += ["--", path_filter]

    raw_diff = repo.git.diff(base_commit.hexsha, head_commit.hexsha, *diff_args)

    # Collect changed files via diff --name-only
    name_args = [base_commit.hexsha, head_commit.hexsha, "--name-only"]
    if path_filter:
        name_args += ["--", path_filter]
    files_raw = repo.git.diff(*name_args)
    files_changed = [f for f in files_raw.splitlines() if f.strip()]

    # Stats via --shortstat
    stat_args = [base_commit.hexsha, head_commit.hexsha, "--shortstat"]
    if path_filter:
        stat_args += ["--", path_filter]
    stat_raw = repo.git.diff(*stat_args)
    additions, deletions, num_files = _parse_shortstat(stat_raw)

    return raw_diff, files_changed, DiffStats(additions=additions, deletions=deletions, files=num_files)


def _parse_shortstat(stat: str) -> tuple[int, int, int]:
    import re
    files = insertions = deletions = 0
    m = re.search(r"(\d+) file", stat)
    if m:
        files = int(m.group(1))
    m = re.search(r"(\d+) insertion", stat)
    if m:
        insertions = int(m.group(1))
    m = re.search(r"(\d+) deletion", stat)
    if m:
        deletions = int(m.group(1))
    return files, insertions, deletions


async def get_diff(
    base_ref: str,
    head_ref: str,
    path_filter: str = "",
    settings: Settings | None = None,
) -> ToolEnvelope:
    t0 = time.monotonic()
    s = settings or get_settings()
    tool = _TOOL_GET_DIFF

    try:
        repo = open_repo(s.git_repo_path)
    except RepoNotConfiguredError as exc:
        return build_error(tool, "REPO_NOT_CONFIGURED", str(exc), False, t0)

    try:
        diff_str, files_changed, stats = await asyncio.wait_for(
            asyncio.to_thread(_diff, repo, base_ref, head_ref, path_filter),
            timeout=s.git_read_timeout_seconds,
        )
    except asyncio.TimeoutError:
        return build_error(tool, "TIMEOUT", f"get_diff timed out after {s.git_read_timeout_seconds}s", True, t0)
    except _RefNotFoundError as exc:
        return build_error(tool, "REF_NOT_FOUND", f"Ref '{exc}' not found", False, t0)

    result = GetDiffResult(diff=diff_str, files_changed=files_changed, stats=stats)
    return build_success(tool, result.model_dump(), t0)


# ---------------------------------------------------------------------------
# Internal exceptions
# ---------------------------------------------------------------------------

class _RefNotFoundError(Exception):
    pass


class _FileNotFoundError(Exception):
    pass
