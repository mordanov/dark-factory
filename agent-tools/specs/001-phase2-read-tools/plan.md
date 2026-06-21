# Implementation Plan: Phase 2 Read Tools — MCP Server

**Branch**: `001-phase2-read-tools` | **Date**: 2026-06-21 | **Spec**: [spec.md](spec.md)

## Summary

Implement the six Phase 2 read-only tools (`read_file`, `list_files`, `search_code`,
`get_diff`, `fetch_project_memory`, `fetch_adrs`) for the Dark Factory Agent Tools
MCP server. Tools are registered via `@mcp.tool()` in a Python 3.12 MCP server,
split into two modules: `src/tools/git_read.py` (four git tools using GitPython)
and `src/tools/document_store.py` (two tools calling Context Distiller over httpx).
Every tool returns the universal envelope. No write operations, no Phase 3 code.

---

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: `mcp` SDK, `GitPython`, `httpx` (async), `pydantic-settings`, `PyJWT`
**Storage**: None — all tools are stateless; no persistent storage in Phase 2
**Testing**: `pytest`, `pytest-asyncio`, `respx` (httpx mock), real `git init` temp repos
**Target Platform**: Linux (Docker container), stdio MCP transport
**Project Type**: MCP server / library
**Performance Goals**: Git read calls ≤ 15 s; Document Store calls ≤ 10 s
**Constraints**: Read-only filesystem access; no public port; no Phase 3 code; path traversal forbidden
**Scale/Scope**: Six tools; one server; consumed by Dark Factory agents via MCP

---

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| Tools are atomic and stateless | PASS | Each tool does exactly one action |
| Universal return envelope | PASS | Every tool returns `ToolEnvelope`; no exceptions escape |
| Idempotent by default | PASS | All six tools are read-only; idempotent by nature |
| FSM-blind | PASS | No FSM imports; no Orchestrator references |
| Phase gate | PASS | No Phase 3 code (`write_file`, `create_pull_request`, etc.) |
| Human approval gate | N/A | `deploy` is Phase 4 |
| Timeout is first-class | PASS | `GIT_READ_TIMEOUT_SECONDS` and `DISTILLER_TIMEOUT_SECONDS` enforced |
| Read tools never write | PASS | GitPython opened read-only; no write methods called |
| Path traversal forbidden | PASS | All paths normalised and validated before use |
| No shell injection | PASS | No subprocess with string interpolation; `repo.git.grep()` used |
| No public HTTP port | PASS | stdio transport only |
| 80% test coverage | PLANNED | Enforced in CI |

---

## Project Structure

### Documentation (this feature)

```text
specs/001-phase2-read-tools/
├── plan.md              ← this file
├── research.md          ← Phase 0: key decisions
├── data-model.md        ← Phase 1: input/output schemas
├── quickstart.md        ← Phase 1: dev setup guide
├── contracts/
│   └── mcp-tools.md     ← Phase 1: MCP tool contracts
└── tasks.md             ← Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
agent-tools/
├── src/
│   ├── server.py              # MCP server entrypoint; registers all 6 tools
│   ├── schemas.py             # Pydantic: ToolEnvelope, ToolError, all input/result models
│   ├── config.py              # Pydantic Settings from .env
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── git_read.py        # read_file, list_files, search_code, get_diff
│   │   └── document_store.py  # fetch_project_memory, fetch_adrs
│   └── utils/
│       ├── __init__.py
│       ├── envelope.py        # build_success() / build_error() helpers
│       ├── git_utils.py       # open_repo(), validate_path(), language_from_ext()
│       └── auth.py            # make_service_jwt() for Distiller HTTP calls
├── tests/
│   ├── conftest.py            # fixtures: tmp_git_repo, mock_distiller
│   ├── test_read_file.py
│   ├── test_list_files.py
│   ├── test_search_code.py
│   ├── test_get_diff.py
│   ├── test_fetch_project_memory.py
│   └── test_fetch_adrs.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── pyproject.toml             # or setup.cfg for pytest config
```

**Structure Decision**: Single project layout (Option 1). No frontend; no separate backend/
api split. All source under `src/`, all tests under `tests/`.

---

## Phase 0: Research — Complete

See [research.md](research.md) for all decisions. Key outcomes:

| Question | Decision |
|---|---|
| Git library | GitPython (`repo.git.grep`, `repo.commit`, blob access) |
| search_code impl | `git grep` via GitPython, wrapped in `asyncio.to_thread` |
| Token truncation | Character proxy: `max_tokens × 4` chars |
| domain_filter | Client-side substring match on title + summary |
| JWT for Distiller | Short-lived HS256 JWT, `python-jose` or `PyJWT` |
| MCP transport | `stdio` (no HTTP port) |
| Async strategy | All tools `async def`; git ops in `asyncio.to_thread` |

---

## Phase 1: Design — Complete

### Module responsibilities

#### `src/config.py`
- `Settings` class (Pydantic BaseSettings)
- Validates `GIT_REPO_PATH` exists and is a git repo on startup
- Exposes singleton `get_settings()` with `lru_cache`

#### `src/schemas.py`
- `ToolError(code, message, retryable)`
- `ToolEnvelope(tool, success, result, error, duration_ms, timestamp)`
- Input models: `ReadFileInput`, `ListFilesInput`, `SearchCodeInput`, `GetDiffInput`, `FetchProjectMemoryInput`, `FetchAdrsInput`
- Result models: `ReadFileResult`, `ListFilesResult`, `SearchCodeResult`, `GetDiffResult`, `FetchProjectMemoryResult`, `FetchAdrsResult`
- `SearchMatch(file, line, content)`, `DiffStats(additions, deletions, files)`, `AdrSummary(id, title, status, summary, date)`

#### `src/utils/envelope.py`
- `build_success(tool_name, result_dict, start_time) → ToolEnvelope`
- `build_error(tool_name, code, message, retryable, start_time) → ToolEnvelope`
- Both capture `duration_ms` from `start_time` and set `timestamp` to current UTC

#### `src/utils/git_utils.py`
- `open_repo(path: str) → git.Repo` — raises `REPO_NOT_CONFIGURED` if invalid
- `validate_path(path: str, repo_root: str) → str` — normalises path, raises `INVALID_INPUT` if `..` escapes root
- `language_from_ext(filename: str) → str` — maps extension to language string

#### `src/utils/auth.py`
- `make_service_jwt(settings: Settings) → str` — generates 60 s HS256 JWT with `sub: "agent-tools"`

#### `src/tools/git_read.py`
Four async tool functions, each:
1. Validate inputs (raise `INVALID_INPUT` envelope on failure)
2. Open repo (raise `REPO_NOT_CONFIGURED` on failure)
3. Validate paths
4. Wrap git operation in `asyncio.wait_for(asyncio.to_thread(...), timeout=settings.git_read_timeout_seconds)`
5. Catch `asyncio.TimeoutError` → `TIMEOUT`; catch `git.exc.BadName` → `REF_NOT_FOUND`; catch `KeyError`/`git.exc.GitCommandError` → `FILE_NOT_FOUND`
6. Build and return `ToolEnvelope`

#### `src/tools/document_store.py`
Two async tool functions, each:
1. Validate inputs
2. Generate JWT via `make_service_jwt`
3. Call Distiller with `httpx.AsyncClient(timeout=settings.distiller_timeout_seconds)`
4. Handle 404 → `MEMORY_NOT_FOUND`; `httpx.ConnectError` / non-2xx → `DISTILLER_UNAVAILABLE`; `httpx.TimeoutException` → `TIMEOUT`
5. Apply `domain_filter` client-side for `fetch_adrs`
6. Apply `max_tokens` character truncation for `fetch_project_memory`

#### `src/server.py`
- Instantiate `mcp = FastMCP("agent-tools")`
- Import and register all 6 tool functions with `@mcp.tool()`
- `if __name__ == "__main__": mcp.run()`

### Testing strategy

| Test file | What it tests |
|---|---|
| `test_read_file.py` | Happy path, `FILE_NOT_FOUND`, `REF_NOT_FOUND`, `INVALID_INPUT` (path traversal), `REPO_NOT_CONFIGURED`, timeout |
| `test_list_files.py` | Happy path (flat + recursive + pattern), `INVALID_INPUT`, `FILE_NOT_FOUND` on non-dir |
| `test_search_code.py` | Happy path, truncation + `truncated: true`, `INVALID_INPUT` (empty query), case insensitive, path_filter, `SEARCH_TIMEOUT` |
| `test_get_diff.py` | Happy path, empty diff (same refs), `REF_NOT_FOUND`, path_filter |
| `test_fetch_project_memory.py` | Happy path, `MEMORY_NOT_FOUND` (404), `DISTILLER_UNAVAILABLE` (connect error), timeout, `max_tokens` truncation |
| `test_fetch_adrs.py` | Happy path, `status_filter`, `domain_filter` (client-side), empty list, `DISTILLER_UNAVAILABLE`, timeout |

All git tests use `conftest.py` fixture `tmp_git_repo` — a real `git.Repo.init()` temp directory with seeded commits.
All Distiller tests use `respx` to mock HTTP responses.

---

## Complexity Tracking

No constitution violations. No complexity tracking required.
