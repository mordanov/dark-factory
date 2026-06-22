# Dark Factory — Agent Tools Constitution

## Identity

Agent Tools is a standalone MCP (Model Context Protocol) server that exposes
atomic, stateless capabilities to Dark Factory agents. It is the execution layer
between an agent's LLM reasoning and the real world: repositories, test runners,
linters, CI systems, and the Document Store.

Agent Tools has no opinions about workflow, FSM state, or business logic.
It executes one action, returns a structured result, and stops.
All interpretation of results belongs to the calling agent or the Orchestrator.

---

## Core Principles

### 1. Tools are atomic and stateless

Every tool executes exactly one action. It does not chain calls, does not remember
previous invocations, and does not maintain session state between calls.
Any tool that needs more than one external call to produce its result must compose
those calls internally and return a single unified response.

### 2. Universal return envelope — no exceptions

Every tool, in every phase, under every condition, must return:

```json
{
  "tool": "tool_name",
  "success": true | false,
  "result": { } | null,
  "error": null | { "code": "string", "message": "string", "retryable": bool },
  "duration_ms": 0,
  "timestamp": "ISO8601"
}
```

A tool must never throw an uncaught exception to the caller.
All errors are caught internally and returned as `success: false` with a structured
`error` object. The caller decides whether to retry.

### 3. Idempotent by default

Read tools are inherently idempotent. Write tools (Phase 3+) must be designed
so that calling them twice with the same arguments produces the same observable
state — not duplicate commits, not duplicate PRs. Where true idempotency is
impossible, the tool must document the side-effect explicitly in its spec.

### 4. FSM-blind

Tools must not import, reference, or depend on the Dark Factory FSM engine,
the Orchestrator's decision logic, or ticket states. A tool receives parameters,
calls an external system, returns a result. It has no knowledge of why it was
called or what the Orchestrator will do with the result.

### 5. Phase gate — no Phase N+1 code in Phase N

Code for Phase 3 (write tools) must not exist in the repository while Phase 2
(read tools) is the active implementation phase. Each phase is a separate
deliverable with its own spec, plan, and task list.
Phase boundaries are hard. Stub files and placeholder functions are forbidden —
they create false confidence and untested surface area.

### 6. Human approval gate for destructive tools

Tools in Phase 4 that mutate production state (`deploy`) must verify the presence
of a signed `human_approval_token` in their input before executing.
This check is performed inside the tool itself, not delegated to the caller.
A deploy call without a valid token must return `success: false`,
`error.code: "APPROVAL_REQUIRED"`, and must not contact the deployment target.

### 7. Timeout is a first-class concern

Every tool that calls an external system must enforce a timeout.
Default timeouts (overridable via environment variables):

| Tool group | Default timeout |
|---|---|
| Git read operations | 15s |
| Linter / static analysis | 60s |
| Test runner | 300s |
| CI trigger / status poll | 30s |
| Deploy | 600s |

A timeout must return `success: false`, `error.code: "TIMEOUT"`, `retryable: true`.

---

## Delivery Phases

The following phases are fixed. Each phase requires a separate `/speckit.specify`
invocation. Do not combine phases in a single spec.

### Phase 2 — Read Tools (current target)
Implement these tools only:

| Tool | Group |
|---|---|
| `read_file` | Git read |
| `list_files` | Git read |
| `search_code` | Git read |
| `get_diff` | Git read |
| `fetch_project_memory` | Document Store |
| `fetch_adrs` | Document Store |

### Phase 3 — Write + Test Tools
`write_file`, `create_pull_request`, `request_review`,
`run_tests`, `write_test`, `get_test_report`, `run_linter`

### Phase 4 — Security + Deploy Tools
`run_security_scan`, `check_dependencies`,
`trigger_ci`, `get_ci_status`, `deploy`

### Phase 7 — Ticket Manager wrappers
`update_ticket_fsm`, `manage_tags`, `create_subtask`
(depends on ticket-manager-extensions being implemented first)

---

## Technology Stack

These choices are fixed for all phases:

| Layer | Technology | Rationale |
|---|---|---|
| Protocol | MCP (Model Context Protocol) | Native to Claude; supports OpenAI tool_use via adapter |
| Language | Python 3.12 | Consistency with all Dark Factory services |
| MCP framework | `mcp` Python SDK (`pip install mcp`) | Official SDK |
| Git operations | `pygit2` or `GitPython` | Phase 2: read-only; Phase 3: write |
| HTTP client | `httpx` (async) | Consistency with other services |
| Config | Pydantic Settings + `.env` | Same pattern across Dark Factory |
| Containerisation | Docker + Docker Compose | Required |
| Test runner (Phase 3) | subprocess in isolated Docker container | Security boundary |

**MCP server entrypoint:** `src/server.py`
**Tool registration:** each tool is a Python function decorated with `@mcp.tool()`
**Tool grouping:** one module per phase group (`src/tools/git_read.py`,
`src/tools/document_store.py`, etc.)

---

## Tool Input / Output Contracts

### Phase 2 — `read_file`
```
Input:
  path: str          — relative to repo root
  ref: str = "main"  — git ref (branch / commit sha / tag)

Output result:
  content: str
  size_bytes: int
  language: str      — inferred from extension; "unknown" if not recognised
```

### Phase 2 — `list_files`
```
Input:
  path: str          — directory path relative to repo root
  recursive: bool = False
  pattern: str = ""  — glob pattern, e.g. "*.py"; empty = all files

Output result:
  files: list[str]   — paths relative to repo root
```

### Phase 2 — `search_code`
```
Input:
  query: str
  path_filter: str = ""   — optional glob to restrict search scope
  case_sensitive: bool = False
  max_results: int = 50   — hard cap; never return more

Output result:
  matches: list[{ file: str, line: int, content: str }]
  truncated: bool          — true if results were capped at max_results
```

### Phase 2 — `get_diff`
```
Input:
  base_ref: str
  head_ref: str
  path_filter: str = ""   — optional glob

Output result:
  diff: str               — unified diff format
  files_changed: list[str]
  stats: { additions: int, deletions: int, files: int }
```

### Phase 2 — `fetch_project_memory`
```
Input:
  project_id: str
  ticket_id: str = ""     — optional; used for relevance filtering
  max_tokens: int = 2000

Output result:
  memory: str             — YAML string from ContextDistiller
  source_ticket_ids: list[str]
```

### Phase 2 — `fetch_adrs`
```
Input:
  project_id: str
  status_filter: str = "accepted"   — accepted | proposed | all
  domain_filter: str = ""           — optional tag

Output result:
  adrs: list[{ id: str, title: str, status: str, summary: str, date: str }]
```

---

## Error Codes (exhaustive list for Phase 2)

| Code | Meaning | Retryable |
|---|---|---|
| `FILE_NOT_FOUND` | Path does not exist at given ref | false |
| `REF_NOT_FOUND` | Git ref does not exist | false |
| `REPO_NOT_CONFIGURED` | `GIT_REPO_PATH` env var missing or invalid | false |
| `SEARCH_TIMEOUT` | search_code exceeded timeout | true |
| `MEMORY_NOT_FOUND` | No project memory exists for project_id | false |
| `DISTILLER_UNAVAILABLE` | ContextDistiller HTTP call failed | true |
| `TIMEOUT` | Generic timeout | true |
| `AUTH_FAILED` | Authentication to external service failed | false |
| `INVALID_INPUT` | Parameter validation failed | false |

No other error codes are permitted in Phase 2.
Phase 3+ introduces additional codes; they must be added via constitution amendment.

---

## Configuration (environment variables)

| Variable | Default | Phase |
|---|---|---|
| `GIT_REPO_PATH` | — | 2 — absolute path to the local repo clone |
| `DISTILLER_BASE_URL` | `http://context-distiller:8001` | 2 |
| `DISTILLER_TIMEOUT_SECONDS` | `10` | 2 |
| `JWT_SECRET_KEY` | — | all — must match Prompt Studio |
| `JWT_ALGORITHM` | `HS256` | all |
| `GIT_READ_TIMEOUT_SECONDS` | `15` | 2 |
| `SEARCH_MAX_RESULTS` | `50` | 2 |
| `GITHUB_TOKEN` | — | 3+ — write operations |
| `CI_PROVIDER` | `github` | 4 |
| `DEPLOY_APPROVAL_SECRET` | — | 4 |

---

## Service Boundaries

Agent Tools owns:
- Tool implementations and their MCP registrations
- Input validation and output envelope construction
- Timeout enforcement
- Error normalisation into standard codes

Agent Tools does NOT own:
- Routing decisions (which tool to call) — that is the agent's responsibility
- FSM state — never reads or writes ticket FSM fields
- Project memory content — fetches from ContextDistiller, never writes directly to MongoDB
- Git repository hosting — operates on a local clone via `GIT_REPO_PATH`

---

## Security Constraints

These apply to all phases and may never be relaxed:

- **Read tools never write.** `read_file`, `list_files`, `search_code`, `get_diff`
  must open repositories in read-only mode. Any code path that results in a write
  operation from a read tool is a critical bug.

- **Path traversal is forbidden.** All `path` parameters must be normalised and
  validated to remain within the repository root before any filesystem operation.
  Paths containing `..` after normalisation must return `INVALID_INPUT`.

- **`deploy` requires `human_approval_token`.** This check is inside the tool,
  not the caller. It cannot be bypassed by any agent prompt.

- **No shell injection.** Tools that invoke subprocesses (Phase 3+: linters,
  test runners) must use `subprocess` with argument lists, never string
  interpolation into shell commands.

- **MCP server does not expose a public HTTP port.** It communicates only via
  stdio or a Unix socket on the internal Docker network. It is never reachable
  from outside the compose network.

---

## Testing Requirements

- Minimum **80% line coverage** enforced in CI
- Every tool must have:
  - A unit test for the happy path
  - A unit test for each defined error code
  - A unit test for timeout behaviour (use `asyncio.timeout` mock)
- Git operations must be tested against a real temporary `git init` repo,
  not mocked filesystem calls
- `fetch_project_memory` and `fetch_adrs` must be tested with a mocked
  ContextDistiller HTTP server (`httpx.MockTransport` or `respx`)
- No real network calls, no real GitHub API, no real CI in tests

---

## Definition of Done (per phase)

A phase is complete when:

1. All tools in the phase are implemented, registered with `@mcp.tool()`,
   and documented with their exact input/output schema
2. All tests pass, coverage ≥ 80%
3. Each tool has been manually tested end-to-end via `mcp dev src/server.py`
4. Docker build succeeds; the container starts and responds to MCP tool listing
5. At least one Dark Factory agent (e.g. `software_architect`) has been tested
   calling `read_file` and `list_files` against the actual repo — not a mock
6. No Phase N+1 tool code exists in the repository

---

## Principles That Must Never Be Violated

- **Never throw unhandled exceptions to the caller.** All errors → `success: false`.
- **Never mix phases.** No Phase 3 code during Phase 2 implementation.
- **Never write from a read tool.** Read tools are read-only at the filesystem level.
- **Never bypass the human approval gate on `deploy`.**
- **Never accept paths with `..` after normalisation.**
- **Never call the Orchestrator or FSM engine directly.**
  Tools are infrastructure. They have no workflow awareness.
