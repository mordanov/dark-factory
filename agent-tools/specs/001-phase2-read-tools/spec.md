# Feature Specification: Phase 2 Read Tools — MCP Server

**Feature Branch**: `001-phase2-read-tools`
**Created**: 2026-06-21
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agent reads a source file from the repository (Priority: P1)

A Dark Factory agent (e.g. `software_architect` or `backend`) needs to inspect an
existing file in the project repository before deciding how to implement a task.
The agent calls `read_file` with a path and an optional git ref, and receives the
file content, its size, and its detected programming language.

**Why this priority**: Without the ability to read files, no other read operation
adds value. This is the foundational capability every agent relies on.

**Independent Test**: Call `read_file` against a known file in a real temporary
git repo; verify the returned content matches the file, size is accurate, and
language is correctly inferred from the extension.

**Acceptance Scenarios**:

1. **Given** a valid file path and a valid git ref, **When** `read_file` is called,
   **Then** the tool returns `success: true` with `content`, `size_bytes`, and
   `language` populated in the result envelope.
2. **Given** a path that does not exist at the given ref, **When** `read_file` is
   called, **Then** the tool returns `success: false` with `error.code: "FILE_NOT_FOUND"`
   and `retryable: false`.
3. **Given** a valid path but a ref that does not exist, **When** `read_file` is
   called, **Then** the tool returns `success: false` with `error.code: "REF_NOT_FOUND"`.
4. **Given** a path containing `..` after normalisation, **When** `read_file` is
   called, **Then** the tool returns `success: false` with `error.code: "INVALID_INPUT"`.
5. **Given** the `GIT_REPO_PATH` environment variable is missing or invalid,
   **When** `read_file` is called, **Then** the tool returns `success: false` with
   `error.code: "REPO_NOT_CONFIGURED"`.

---

### User Story 2 — Agent lists files in a directory to understand project structure (Priority: P1)

An agent needs to enumerate files in a directory (optionally recursively, optionally
filtered by glob) before planning changes or reviewing code structure.
The agent calls `list_files` and receives a flat list of paths relative to the
repository root.

**Why this priority**: Directory enumeration is a prerequisite for code navigation
and is called by the majority of agents on every task.

**Independent Test**: Call `list_files` on a real temporary git repo directory
with `recursive: false`, `recursive: true`, and with a `*.py` pattern; verify
each returns only the expected paths.

**Acceptance Scenarios**:

1. **Given** a valid directory path and `recursive: false`, **When** `list_files`
   is called, **Then** only direct children of that directory are returned.
2. **Given** a valid directory path and `recursive: true`, **When** `list_files`
   is called, **Then** all descendant paths (any depth) are returned.
3. **Given** a `pattern` of `"*.py"`, **When** `list_files` is called,
   **Then** only files matching the glob pattern are included.
4. **Given** a path containing `..` after normalisation, **When** `list_files`
   is called, **Then** `INVALID_INPUT` is returned.

---

### User Story 3 — Agent searches for a symbol or pattern across the codebase (Priority: P2)

The `code_reviewer` or `security_architect` agent needs to find all occurrences of
a function name, import, or pattern before performing a review.
The agent calls `search_code` with a query string and optional path filter,
and receives a list of matching file locations with line numbers and content snippets.

**Why this priority**: Search enables targeted analysis; agents can operate without
it by reading individual files, but at far higher token cost and lower accuracy.

**Independent Test**: Seed a temporary repo with known content, call `search_code`
for a unique string, and verify the returned matches contain the correct file, line
number, and content. Also verify `truncated: true` when results exceed `max_results`.

**Acceptance Scenarios**:

1. **Given** a query that matches multiple lines in the repo, **When** `search_code`
   is called, **Then** each match contains `file`, `line`, and `content` fields.
2. **Given** a `path_filter` glob, **When** `search_code` is called, **Then**
   only files matching the filter are searched.
3. **Given** `case_sensitive: false` and a mixed-case query, **When** `search_code`
   is called, **Then** matches are returned regardless of case.
4. **Given** results exceed `max_results`, **When** `search_code` is called,
   **Then** at most `max_results` matches are returned and `truncated: true` is set.
5. **Given** the search exceeds the configured timeout, **When** `search_code`
   is called, **Then** `error.code: "SEARCH_TIMEOUT"` and `retryable: true` are returned.

---

### User Story 4 — Agent reviews changes between two git refs (Priority: P2)

The `code_reviewer` or `autotester` agent needs to inspect the diff between a feature
branch and main before performing a review or generating tests.
The agent calls `get_diff` with `base_ref` and `head_ref`, optionally scoped to a
path filter, and receives the unified diff, the list of changed files, and change statistics.

**Why this priority**: Diff access is critical for review and testing workflows, but
agents can fall back to full file reads, making it lower priority than file access.

**Independent Test**: Create two commits in a temporary repo, call `get_diff` between
them, and verify the unified diff string, `files_changed` list, and `stats` match the
actual changes.

**Acceptance Scenarios**:

1. **Given** valid `base_ref` and `head_ref`, **When** `get_diff` is called,
   **Then** `diff` contains a valid unified diff, `files_changed` lists affected
   paths, and `stats` contains `additions`, `deletions`, and `files` counts.
2. **Given** a `path_filter` glob, **When** `get_diff` is called, **Then** only
   files matching the filter appear in the diff.
3. **Given** either ref does not exist, **When** `get_diff` is called, **Then**
   `error.code: "REF_NOT_FOUND"` is returned.
4. **Given** the refs are identical, **When** `get_diff` is called, **Then**
   an empty diff with zero stats is returned successfully.

---

### User Story 5 — Orchestrator injects project memory into an agent's context (Priority: P1)

Before dispatching a task to an agent, the Orchestrator calls `fetch_project_memory`
with a `project_id` (and optionally a `ticket_id` for relevance filtering) to retrieve
the compressed YAML project memory from the Context Distiller service.
The result is injected into the agent's prompt as background context.

**Why this priority**: Project memory provides accumulated decisions and context that
prevent agents from repeating resolved discussions. It is injected on every agent
dispatch, making it as foundational as file reading.

**Independent Test**: Mock the Context Distiller HTTP endpoint; call
`fetch_project_memory` and verify the returned `memory` YAML string and
`source_ticket_ids` list match the mock response. Also verify
`DISTILLER_UNAVAILABLE` is returned when the endpoint is unreachable.

**Acceptance Scenarios**:

1. **Given** a valid `project_id` with existing memory, **When**
   `fetch_project_memory` is called, **Then** `memory` contains a YAML string and
   `source_ticket_ids` lists contributing ticket IDs.
2. **Given** a `project_id` with no memory stored, **When**
   `fetch_project_memory` is called, **Then** `error.code: "MEMORY_NOT_FOUND"` is
   returned with `retryable: false`.
3. **Given** the Context Distiller service is unreachable, **When**
   `fetch_project_memory` is called, **Then** `error.code: "DISTILLER_UNAVAILABLE"`
   and `retryable: true` are returned.
4. **Given** a `max_tokens` value, **When** `fetch_project_memory` is called,
   **Then** the returned memory does not exceed that token count.

---

### User Story 6 — Agent or Orchestrator retrieves architectural decision records (Priority: P2)

The `software_architect` or Orchestrator calls `fetch_adrs` to retrieve a list of
accepted (or filtered) ADRs for a project, optionally narrowed by domain tag.
The agent uses the ADR summaries to understand architectural constraints before
proposing or reviewing code changes.

**Why this priority**: ADRs inform design decisions but are less frequently needed
than live project memory. Most agents can proceed without them on routine tasks.

**Independent Test**: Mock the Context Distiller ADR endpoint; call `fetch_adrs`
with `status_filter: "accepted"` and with `domain_filter: "auth"`, and verify
the returned list structure and filtering behaviour.

**Acceptance Scenarios**:

1. **Given** a valid `project_id`, **When** `fetch_adrs` is called with
   `status_filter: "accepted"`, **Then** only ADRs with status `"accepted"` are
   returned.
2. **Given** a `domain_filter` tag, **When** `fetch_adrs` is called, **Then**
   only ADRs tagged with that domain are included.
3. **Given** `status_filter: "all"`, **When** `fetch_adrs` is called, **Then**
   ADRs of all statuses are returned.
4. **Given** no ADRs exist for the project, **When** `fetch_adrs` is called,
   **Then** `success: true` with an empty `adrs` list is returned.
5. **Given** the Context Distiller service is unreachable, **When** `fetch_adrs`
   is called, **Then** `error.code: "DISTILLER_UNAVAILABLE"` and `retryable: true`
   are returned.

---

### Edge Cases

- What happens when a file path is valid but the file is binary (e.g. an image)?
  The tool returns the raw bytes decoded as UTF-8 where possible, or a size-only
  response with `language: "binary"` and a truncation notice.
- How does the system handle a `ref` of a commit SHA that exists but is detached?
  The tool resolves the SHA directly; it does not require a branch name.
- What happens when `list_files` is called on a path that is a file, not a directory?
  The tool returns `INVALID_INPUT`.
- What happens when `search_code` is called with an empty `query`?
  The tool returns `INVALID_INPUT`.
- What happens when both `GIT_REPO_PATH` is set but points to a non-git directory?
  The tool returns `REPO_NOT_CONFIGURED`.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The MCP server MUST expose all six Phase 2 tools (`read_file`,
  `list_files`, `search_code`, `get_diff`, `fetch_project_memory`, `fetch_adrs`)
  registered via `@mcp.tool()` in `src/server.py`.
- **FR-002**: Every tool MUST return the standard envelope:
  `{ tool, success, result, error, duration_ms, timestamp }` under all conditions,
  including internal errors and timeouts.
- **FR-003**: The four git read tools (`read_file`, `list_files`, `search_code`,
  `get_diff`) MUST operate on a local repository clone identified by the
  `GIT_REPO_PATH` environment variable and MUST open the repository in read-only mode.
- **FR-004**: All `path` parameters MUST be normalised and validated to remain within
  the repository root. Any path containing `..` after normalisation MUST be rejected
  with `error.code: "INVALID_INPUT"`.
- **FR-005**: `read_file` MUST accept a `ref` parameter (default: `"main"`) and
  return `content`, `size_bytes`, and `language` (inferred from file extension;
  `"unknown"` if unrecognised).
- **FR-006**: `list_files` MUST support `recursive` (default: `false`) and `pattern`
  (default: `""`, meaning all files) parameters and return paths relative to the
  repository root.
- **FR-007**: `search_code` MUST support `path_filter`, `case_sensitive`
  (default: `false`), and `max_results` (default: 50, hard cap) parameters.
  Results MUST include `file`, `line`, and `content` per match, and MUST set
  `truncated: true` when the cap is reached.
- **FR-008**: `get_diff` MUST accept `base_ref`, `head_ref`, and optional
  `path_filter`, and return `diff` (unified format), `files_changed`, and
  `stats: { additions, deletions, files }`.
- **FR-009**: `fetch_project_memory` MUST call the Context Distiller HTTP API
  (`GET /api/v1/memory/{project_id}`), passing authentication via JWT, and
  return `memory` (YAML string) and `source_ticket_ids`.
- **FR-010**: `fetch_adrs` MUST call the Context Distiller HTTP API
  (`GET /api/v1/memory/{project_id}/adrs`) with optional `status` and
  `domain_filter` query parameters, and return a list of ADR summaries with
  `id`, `title`, `status`, `summary`, and `date` fields.
- **FR-011**: Every tool MUST enforce the timeout defined for its group
  (git read: `GIT_READ_TIMEOUT_SECONDS`, default 15 s; HTTP calls:
  `DISTILLER_TIMEOUT_SECONDS`, default 10 s). A timeout MUST return
  `error.code: "TIMEOUT"` with `retryable: true`.
- **FR-012**: The MCP server MUST start and respond to the MCP tool listing call
  inside a Docker container built from the project's `Dockerfile`.
- **FR-013**: The tool suite MUST achieve a minimum of 80% line coverage in CI.
  Every tool MUST have a unit test for its happy path, for each defined error code,
  and for timeout behaviour.
- **FR-014**: Git read tools MUST be tested against a real temporary `git init`
  repository, not a mocked filesystem.
- **FR-015**: `fetch_project_memory` and `fetch_adrs` MUST be tested with a mocked
  Context Distiller HTTP server (`httpx.MockTransport` or `respx`); no real network
  calls are permitted in tests.
- **FR-016**: No Phase 3 tool code (`write_file`, `create_pull_request`, etc.) MAY
  exist anywhere in the repository while Phase 2 is the active phase.

### Key Entities

- **Tool Envelope**: The standard response wrapper returned by every tool —
  carries `tool` name, `success` flag, `result` payload, `error` object,
  `duration_ms`, and ISO 8601 `timestamp`.
- **Git Read Tools**: The four tools (`read_file`, `list_files`, `search_code`,
  `get_diff`) that operate against a local repository clone. They share
  `GIT_REPO_PATH` configuration and read-only access constraints.
- **Document Store Tools**: The two tools (`fetch_project_memory`, `fetch_adrs`)
  that call the Context Distiller service over HTTP and return structured memory
  or ADR data.
- **Context Distiller**: The upstream service (running at `DISTILLER_BASE_URL`,
  default `http://context-distiller:8001`) that owns project memory and ADR
  storage. Agent Tools fetches from it but never writes directly to its database.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All six Phase 2 tools are callable by a Dark Factory agent end-to-end
  against the actual repository — no mocks — within a single test session.
- **SC-002**: Every tool returns a correctly structured response envelope within its
  configured timeout under normal operating conditions (git read ≤ 15 s,
  Document Store ≤ 10 s).
- **SC-003**: The test suite passes with ≥ 80% line coverage across all Phase 2
  tool modules in CI.
- **SC-004**: The Docker container builds successfully, starts, and lists all six
  tools in response to an MCP tool-listing request within 30 seconds of container
  start.
- **SC-005**: Path traversal attempts (`../etc/passwd` style inputs) are rejected
  by all four git read tools with `INVALID_INPUT`, confirmed by dedicated test cases.
- **SC-006**: When the Context Distiller service is unavailable, `fetch_project_memory`
  and `fetch_adrs` return a retryable error within the configured timeout —
  agents are never left waiting indefinitely.
- **SC-007**: No Phase 3 code exists in the repository at merge time, confirmed by
  a CI check or code review gate.

---

## Assumptions

- The local git repository clone is already present at `GIT_REPO_PATH` before the
  MCP server starts; the server does not clone or fetch the repo itself.
- The Context Distiller service is reachable on the internal Docker Compose network
  at `DISTILLER_BASE_URL`; no public internet access is required.
- JWT authentication uses the same `JWT_SECRET_KEY` and `HS256` algorithm already
  configured across Dark Factory services (Prompt Studio, Orchestrator).
- The ADR `domain_filter` parameter performs a tag-based filter; the Context
  Distiller already stores domain tags on each ADR record and supports filtering
  via query parameter.
- Binary files returned by `read_file` are decoded as UTF-8 where possible; the
  tool does not implement separate binary download semantics in Phase 2.
- `fetch_project_memory` returns the full memory document from Context Distiller;
  token truncation to `max_tokens` is performed client-side within the tool before
  returning the result.
- The MCP server communicates via stdio or Unix socket only; no HTTP port is exposed
  outside the Docker Compose network.
- Phase 2 tooling is sufficient for at least one agent (`software_architect`) to
  perform a meaningful read-only code review workflow before Phase 3 begins.
