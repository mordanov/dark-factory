# Research: Phase 2 Read Tools

**Date**: 2026-06-21
**Branch**: `001-phase2-read-tools`

---

## Decision 1: Git library — GitPython vs pygit2

**Decision**: Use `GitPython` for Phase 2.

**Rationale**: Both are allowed by the constitution. GitPython wraps `git` subprocess
commands (including `git grep`) which maps directly to Phase 2 operations without
requiring low-level object traversal. `pygit2` is faster and purely native but
requires libgit2 to be installed in the Docker image and is more verbose for
read-only path resolution and diff generation. Phase 2 is read-only; the
performance delta is negligible at the call rates expected from LLM agents.
GitPython is the lower-risk choice for the first phase. `pygit2` can replace it
in a later phase if profiling reveals a bottleneck.

**Alternatives considered**:
- `pygit2` — faster, no subprocess overhead, but adds libgit2 C dependency to Docker image.
- `subprocess git` directly — fragile, shell injection surface, no safety guarantees.

---

## Decision 2: search_code implementation strategy

**Decision**: Use `repo.git.grep()` (GitPython's wrapper around `git grep`) with
`--line-number` and `--ignore-case` flags as appropriate.

**Rationale**: `git grep` is the canonical, battle-tested tool for searching
repository content at a given ref. It is fast, respects `.gitignore`, handles
binary file detection natively, and does not require loading all blobs into memory.
The `SEARCH_TIMEOUT` enforcement wraps the call in `asyncio.wait_for`.

**Alternatives considered**:
- Python `re` over all blobs: loads all file content into memory, very slow for large repos.
- `ripgrep` subprocess: fast but adds another binary dependency and requires shell escaping care.

---

## Decision 3: Token truncation for fetch_project_memory

**Decision**: Use a character-count proxy (1 token ≈ 4 characters) to enforce
`max_tokens`. Truncate the YAML string at `max_tokens * 4` characters and append
a `# [TRUNCATED]` marker.

**Rationale**: Adding `tiktoken` solely for this one tool would increase the
image size and add a network dependency for tokenizer downloads. The 4-char
approximation is accurate to within ~15% for YAML-formatted English text, which
is sufficient for a "good enough" context window budget hint. The Orchestrator
already knows the exact token count once the string is in the LLM context.

**Alternatives considered**:
- `tiktoken`: accurate but adds ~50 MB dependency and network download.
- Word count: less accurate than character count for YAML (whitespace-heavy).

---

## Decision 4: domain_filter for fetch_adrs

**Decision**: Apply `domain_filter` client-side after fetching from Context Distiller,
by substring-matching the filter value against each ADR's `title` and `summary` fields.

**Rationale**: The Context Distiller `GET /api/v1/memory/{project_id}/adrs` endpoint
(confirmed from sibling project source) accepts only `status` as a query parameter.
There is no `domain_filter` query param in the current CD API. Rather than requiring
a CD API change in Phase 2 scope, we filter client-side. This is documented as a
known limitation; a CD API extension can be added in a future phase.

**Alternatives considered**:
- Extend CD API: correct long-term solution, out of Phase 2 scope.
- Ignore domain_filter: violates the tool contract defined in constitution.

---

## Decision 5: JWT generation for Context Distiller calls

**Decision**: Generate a short-lived JWT inside the tool using `python-jose` (or
`PyJWT`) with `JWT_SECRET_KEY` and `JWT_ALGORITHM=HS256` before each HTTP call.
The token payload carries `{"sub": "agent-tools", "iat": now}` with a 60-second
expiry.

**Rationale**: Context Distiller's `/api/v1/memory/` endpoints require
`Authorization: Bearer <token>` (confirmed from `src/api/dependencies.py` in
sibling project). The agent-tools server needs to authenticate as a service client.
Using the shared secret key (already required for all Dark Factory services) with
a short expiry token is the simplest approach consistent with existing auth patterns.

**Alternatives considered**:
- Static API key: not supported by CD's current auth middleware.
- Long-lived JWT: security anti-pattern; short-lived tokens are the correct choice.

---

## Decision 6: MCP server transport

**Decision**: Use `stdio` transport (`mcp.run()` default) for Docker deployment,
as mandated by the constitution ("MCP server does not expose a public HTTP port").

**Rationale**: The `mcp` Python SDK supports `stdio` and `SSE` transports. `stdio`
is the correct choice: it communicates only through stdin/stdout within the Docker
network, is invisible to external networks, and is the mode used by Claude Desktop
and the Dark Factory agent runtime.

**Alternatives considered**:
- SSE/HTTP: exposes a port, violates the security constraint in the constitution.

---

## Decision 7: Async vs sync tool functions

**Decision**: All tool functions are `async def`. The MCP server runs in an `asyncio`
event loop. Git operations (GitPython) are wrapped in `asyncio.to_thread()` since
GitPython is synchronous. httpx calls use the async client natively.

**Rationale**: The `mcp` Python SDK is async-native. Blocking the event loop with
synchronous git operations would stall all concurrent tool calls. `asyncio.to_thread`
is the standard solution for wrapping blocking I/O in an async context.

---

## Resolved: Context Distiller integration contract

Confirmed from `dark-factory/context-distiller/src/api/v1/memory.py`:

| Operation | Method + Path | Auth | Key fields |
|---|---|---|---|
| Get project memory | `GET /api/v1/memory/{project_id}` | Bearer JWT | `content` (YAML str), `last_ticket_id` |
| List ADRs | `GET /api/v1/memory/{project_id}/adrs?status={status}` | Bearer JWT | `adrs[].id/title/status/summary/created_at` |

The `source_ticket_ids` return field in `fetch_project_memory` maps to `[last_ticket_id]`
when the field is non-empty, or `[]` otherwise.

The `date` field in ADR summaries maps to `created_at` from `AdrSummary`.
