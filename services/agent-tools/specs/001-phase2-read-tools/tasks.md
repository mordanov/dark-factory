# Tasks: Phase 2 Read Tools — MCP Server

**Input**: Design documents from `specs/001-phase2-read-tools/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/mcp-tools.md ✓

**Tests**: Included — required by FR-013, FR-014, FR-015 (not optional for this feature).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US6, maps to spec.md)

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Create the project skeleton — directories, config files, dependencies, Docker.
No source logic in this phase.

- [x] T001 Create directory structure: `src/`, `src/tools/`, `src/utils/`, `tests/`
- [x] T002 Create `requirements.txt` with: `mcp`, `GitPython`, `httpx`, `pydantic-settings`, `PyJWT`, `pytest`, `pytest-asyncio`, `respx`, `pytest-cov`
- [x] T003 [P] Create `pyproject.toml` with pytest config: `asyncio_mode = "auto"`, `--cov=src`, `--cov-fail-under=80`
- [x] T004 [P] Create `Dockerfile`: Python 3.12 slim, install requirements, `CMD ["python", "src/server.py"]`
- [x] T005 [P] Create `docker-compose.yml`: `agent-tools` service with `stdin_open: true`, `GIT_REPO_PATH` volume mount, `context-distiller` network
- [x] T006 [P] Create `.env.example` with all variables from constitution: `GIT_REPO_PATH`, `JWT_SECRET_KEY`, `DISTILLER_BASE_URL`, `DISTILLER_TIMEOUT_SECONDS`, `GIT_READ_TIMEOUT_SECONDS`, `SEARCH_MAX_RESULTS`, `JWT_ALGORITHM`

**Checkpoint**: Project skeleton exists; `docker build .` succeeds (no source yet).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure that ALL user stories depend on. Must complete before any story begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T007 Create `src/config.py`: `Settings` (Pydantic BaseSettings) with all env vars from `.env.example`; `get_settings()` with `@lru_cache`; validate `GIT_REPO_PATH` exists on startup
- [x] T008 Create `src/schemas.py`: `ToolError`, `ToolEnvelope`; input models `ReadFileInput`, `ListFilesInput`, `SearchCodeInput`, `GetDiffInput`, `FetchProjectMemoryInput`, `FetchAdrsInput`; result models `ReadFileResult`, `ListFilesResult`, `SearchCodeResult`, `GetDiffResult`, `FetchProjectMemoryResult`, `FetchAdrsResult`; helper models `SearchMatch`, `DiffStats`, `AdrSummary`
- [x] T009 [P] Create `src/utils/envelope.py`: `build_success(tool_name, result_dict, start_time) -> ToolEnvelope` and `build_error(tool_name, code, message, retryable, start_time) -> ToolEnvelope`; both compute `duration_ms` and ISO 8601 `timestamp`
- [x] T010 [P] Create `src/utils/git_utils.py`: `open_repo(path) -> git.Repo` (raises `REPO_NOT_CONFIGURED`); `validate_path(path, repo_root) -> str` (normalises, raises `INVALID_INPUT` if `..` escapes root); `language_from_ext(filename) -> str` (maps extensions per data-model.md language table)
- [x] T011 [P] Create `src/utils/auth.py`: `make_service_jwt(settings) -> str` — HS256 JWT with `sub="agent-tools"`, 60 s expiry, using `PyJWT`
- [x] T012 Create `src/tools/__init__.py` and `src/utils/__init__.py` (empty)
- [x] T013 Create `src/server.py`: instantiate `mcp = FastMCP("agent-tools")`; `if __name__ == "__main__": mcp.run()`; no tool registrations yet
- [x] T014 Create `tests/conftest.py`: `tmp_git_repo` fixture (real `git.Repo.init()` temp dir with at least two commits and a known file); `mock_distiller` fixture using `respx.MockRouter` that intercepts `DISTILLER_BASE_URL`; `settings_with_tmp_repo` fixture

**Checkpoint**: Foundation ready — all utilities exist, server starts, fixtures available. User story phases may now begin.

---

## Phase 3: User Story 1 — Agent Reads a File (Priority: P1) 🎯 MVP

**Goal**: `read_file` is callable, returns content + size + language, handles all error cases.

**Independent Test**: `mcp dev src/server.py` → call `read_file` on `README.md` at `main`; verify content matches file, `language` is inferred, `success: true`.

- [x] T015 [US1] Write `tests/test_read_file.py`: happy path (content, size_bytes, language); `FILE_NOT_FOUND` (missing path); `REF_NOT_FOUND` (bad ref); `INVALID_INPUT` (path with `../`); `REPO_NOT_CONFIGURED` (invalid `GIT_REPO_PATH`); timeout (mock `asyncio.to_thread` to delay past `GIT_READ_TIMEOUT_SECONDS`). Confirm tests FAIL before T016.
- [x] T016 [US1] Implement `read_file` in `src/tools/git_read.py`: async function; validate path; open repo; `asyncio.wait_for(asyncio.to_thread(...))` for blob fetch at ref; catch `asyncio.TimeoutError → TIMEOUT`, `git.exc.BadName → REF_NOT_FOUND`, missing blob → `FILE_NOT_FOUND`; return `ToolEnvelope` via `build_success`/`build_error`. Register with `@mcp.tool()` in `src/server.py`.

**Checkpoint**: `tests/test_read_file.py` passes. User Story 1 independently functional.

---

## Phase 4: User Story 2 — Agent Lists Directory Files (Priority: P1)

**Goal**: `list_files` is callable, returns sorted relative paths with recursive and glob filter support.

**Independent Test**: `mcp dev src/server.py` → call `list_files` on `src/` with `recursive: true`, `pattern: "*.py"`; verify only `.py` paths returned.

- [x] T017 [US2] Write `tests/test_list_files.py`: happy path flat; happy path recursive; glob pattern filter; empty result (no matches); `INVALID_INPUT` (path with `../`; path is a file not a dir); `REPO_NOT_CONFIGURED`. Confirm tests FAIL before T018.
- [x] T018 [US2] Add `list_files` to `src/tools/git_read.py`: async function; validate path; open repo; traverse tree at `HEAD` (default); apply `recursive` and `pattern` (fnmatch); return sorted `files` list. Register with `@mcp.tool()` in `src/server.py`.

**Checkpoint**: `tests/test_list_files.py` passes. User Story 2 independently functional.

---

## Phase 5: User Story 5 — Orchestrator Fetches Project Memory (Priority: P1)

**Goal**: `fetch_project_memory` is callable, returns YAML memory from Context Distiller, handles unavailability and token truncation.

**Independent Test**: With `mock_distiller` returning a known YAML payload, call `fetch_project_memory`; verify `memory` and `source_ticket_ids` match mock; verify `DISTILLER_UNAVAILABLE` when mock errors.

- [x] T019 [US5] Write `tests/test_fetch_project_memory.py`: happy path (YAML memory, source_ticket_ids); `MEMORY_NOT_FOUND` (404 from mock); `DISTILLER_UNAVAILABLE` (connection error); `TIMEOUT` (httpx timeout); `max_tokens` truncation (content ends with `# [TRUNCATED]`). Confirm tests FAIL before T020.
- [x] T020 [US5] Create `src/tools/document_store.py` with `fetch_project_memory`: generate JWT via `make_service_jwt`; `GET {DISTILLER_BASE_URL}/api/v1/memory/{project_id}` with `httpx.AsyncClient(timeout=...)`; map 404 → `MEMORY_NOT_FOUND`, `ConnectError` → `DISTILLER_UNAVAILABLE`, `TimeoutException` → `TIMEOUT`; apply `max_tokens × 4` char truncation; extract `source_ticket_ids` from `last_ticket_id`. Register with `@mcp.tool()` in `src/server.py`.

**Checkpoint**: `tests/test_fetch_project_memory.py` passes. User Story 5 independently functional.

---

## Phase 6: User Story 3 — Agent Searches Codebase (Priority: P2)

**Goal**: `search_code` is callable, returns match list with file/line/content, respects max_results cap and path_filter.

**Independent Test**: Seed `tmp_git_repo` with a known string; call `search_code` for that string; verify match count, file, line, content. Call with 51 results available and `max_results: 50`; verify `truncated: true`.

- [x] T021 [US3] Write `tests/test_search_code.py`: happy path (correct file/line/content); case-insensitive match; path_filter restricts scope; truncation at max_results + `truncated: true`; `INVALID_INPUT` (empty query); `SEARCH_TIMEOUT` (mock timeout); `REPO_NOT_CONFIGURED`. Confirm tests FAIL before T022.
- [x] T022 [US3] Add `search_code` to `src/tools/git_read.py`: async function; validate non-empty query; open repo; `asyncio.wait_for(asyncio.to_thread(repo.git.grep, ...), timeout=GIT_READ_TIMEOUT_SECONDS)`; parse grep output into `SearchMatch` list; apply `max_results` cap and set `truncated`; catch `asyncio.TimeoutError → SEARCH_TIMEOUT`. Register with `@mcp.tool()` in `src/server.py`.

**Checkpoint**: `tests/test_search_code.py` passes. User Story 3 independently functional.

---

## Phase 7: User Story 4 — Agent Reviews Diff Between Refs (Priority: P2)

**Goal**: `get_diff` is callable, returns unified diff, files_changed list, and addition/deletion stats for two refs.

**Independent Test**: Create two commits in `tmp_git_repo` (add a line); call `get_diff`; verify `diff` is non-empty, `files_changed` includes the modified file, `stats.additions >= 1`.

- [x] T023 [US4] Write `tests/test_get_diff.py`: happy path (diff content, files_changed, stats); empty diff (identical refs); `REF_NOT_FOUND` (bad ref); path_filter restricts diff scope; timeout. Confirm tests FAIL before T024.
- [x] T024 [US4] Add `get_diff` to `src/tools/git_read.py`: async function; open repo; `asyncio.to_thread(repo.git.diff, base_ref, head_ref, ...)` with unified format; parse `--stat`-style output for stats; apply `path_filter` if provided; catch `git.exc.BadName → REF_NOT_FOUND`. Register with `@mcp.tool()` in `src/server.py`.

**Checkpoint**: `tests/test_get_diff.py` passes. User Story 4 independently functional.

---

## Phase 8: User Story 6 — Agent Fetches Architectural Decision Records (Priority: P2)

**Goal**: `fetch_adrs` is callable, returns filtered ADR list from Context Distiller with status and domain filtering.

**Independent Test**: With `mock_distiller` returning 3 ADRs (2 accepted, 1 proposed), call `fetch_adrs` with `status_filter: "accepted"`; verify only 2 returned. Call with `domain_filter: "auth"` where only 1 matches; verify 1 returned.

- [x] T025 [US6] Write `tests/test_fetch_adrs.py`: happy path with `status_filter: "accepted"`; `status_filter: "all"` returns all; `domain_filter` client-side match; empty result (no ADRs); `DISTILLER_UNAVAILABLE`; `TIMEOUT`. Confirm tests FAIL before T026.
- [x] T026 [US6] Add `fetch_adrs` to `src/tools/document_store.py`: generate JWT; `GET {DISTILLER_BASE_URL}/api/v1/memory/{project_id}/adrs?status={status_filter}` (pass `"accepted"/"proposed"` or omit for `"all"`); map `ConnectError → DISTILLER_UNAVAILABLE`, `TimeoutException → TIMEOUT`; apply `domain_filter` as substring match on `title + summary` client-side; map `AdrSummary.created_at` → `date` ISO string. Register with `@mcp.tool()` in `src/server.py`.

**Checkpoint**: `tests/test_fetch_adrs.py` passes. All 6 user stories independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation, coverage enforcement, Docker verification, catalog update.

- [x] T027 Run full test suite: `pytest tests/ -v --cov=src --cov-report=term-missing`; confirm all tests pass and line coverage ≥ 80% across `src/tools/git_read.py`, `src/tools/document_store.py`, `src/utils/`
- [x] T028 [P] Verify Docker build: `docker build -t agent-tools .` succeeds; `docker run --rm -i -e GIT_REPO_PATH=/tmp agent-tools python -c "from src.server import mcp; print(len(mcp.list_tools()))"` prints `6`
- [x] T029 [P] Audit repo for Phase 3 code: `grep -r "write_file\|create_pull_request\|request_review\|run_tests\|write_test\|run_linter" src/`; output must be empty
- [x] T030 Update `agent-tools-catalog.md`: change status of `read_file`, `list_files`, `search_code`, `get_diff`, `fetch_project_memory`, `fetch_adrs` from `planned` → `available`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1/Phase 3, US2/Phase 4, US5/Phase 5**: All depend on Phase 2; can run in parallel with each other
- **US3/Phase 6, US4/Phase 7, US6/Phase 8**: All depend on Phase 2; can run in parallel; may start before Phase 3–5 complete
- **Polish (Phase 9)**: Depends on all story phases complete

### User Story Dependencies

| Story | Depends on | Can parallelize with |
|---|---|---|
| US1 — read_file | Phase 2 complete | US2, US5 |
| US2 — list_files | Phase 2 complete | US1, US5 |
| US5 — fetch_project_memory | Phase 2 complete | US1, US2 |
| US3 — search_code | Phase 2 complete | US4, US6 |
| US4 — get_diff | Phase 2 complete | US3, US6 |
| US6 — fetch_adrs | Phase 2 complete | US3, US4 |

### Within Each User Story

1. Write tests → confirm they FAIL
2. Implement tool function
3. Register in `src/server.py`
4. Run story tests → confirm they PASS
5. Checkpoint

### Parallel Opportunities

- T003–T006 in Phase 1 can all run in parallel
- T009–T011 in Phase 2 can run in parallel (different utility files)
- US1 (T015–T016), US2 (T017–T018), US5 (T019–T020) can run in parallel after Phase 2
- US3 (T021–T022), US4 (T023–T024), US6 (T025–T026) can run in parallel after Phase 2
- T028–T029 in Phase 9 can run in parallel

---

## Parallel Example: P1 Stories (after Phase 2)

```
Parallel stream A — US1:
  T015: Write tests/test_read_file.py
  T016: Implement + register read_file

Parallel stream B — US2:
  T017: Write tests/test_list_files.py
  T018: Implement + register list_files

Parallel stream C — US5:
  T019: Write tests/test_fetch_project_memory.py
  T020: Implement + register fetch_project_memory (new file: document_store.py)
```

---

## Implementation Strategy

### MVP First (US1 only — single tool end-to-end)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 (read_file)
4. **STOP and VALIDATE**: `mcp dev src/server.py` → call `read_file` on a real file
5. Confirm the agent can read a file; extend to remaining stories

### Incremental Delivery

1. Phase 1 + 2 → foundation ready
2. Phase 3 (read_file) → first tool live, demo-able
3. Phase 4 (list_files) → agents can navigate structure
4. Phase 5 (fetch_project_memory) → Orchestrator injection works
5. Phase 6–8 (search, diff, ADRs) → full Phase 2 capability
6. Phase 9 → ship

### Notes

- `[P]` tasks = operate on different files, no in-flight dependencies
- Each story phase ends at a named checkpoint — stop there to validate before proceeding
- Tests must fail before implementation (write test → confirm red → implement → confirm green)
- `src/tools/git_read.py` grows across US1–US4: each story appends a new function; do not stub ahead
- `src/tools/document_store.py` is created at US5 (T020) and extended at US6 (T026)
- `src/server.py` receives one new `@mcp.tool()` registration per story phase
