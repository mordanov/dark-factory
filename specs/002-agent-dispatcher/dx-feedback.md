# DX Feedback: contracts/api.md — Agent Dispatcher Service

**Author**: designer agent  
**Date**: 2026-06-22  
**Scope**: `specs/002-agent-dispatcher/contracts/api.md`  
**Audience**: backend (implementor), code-reviewer, autotester  
**Priority**: Address blocking findings before Phase 3 implementation begins.

---

## Summary

The contracts are well-structured and internally consistent for the happy path. Five issues
need resolution before implementation to avoid confusing API consumers; three are minor
polish suggestions.

---

## Blocking Findings

### DX-001 — `result.status` vs run `status` are different enums — document explicitly

**Location**: `AgentRunResponse`, `AgentResult`, `[RESULT]` block contract  
**Problem**: `AgentRunResponse.status` has 6 values (`pending`, `running`, `completed`,
`needs_review`, `failed`, `timed_out`) while `AgentResult.status` (the nested `result`
field) has 3 different values (`completed`, `needs_review`, `blocked`). Both fields are
named `status` in the JSON response. A developer reading the API response will reasonably
assume they are the same set and write code against the wrong values.

Furthermore, `blocked` is a valid `AgentResult.status` value but does NOT exist in the
`agent_run_status` enum. The contract does not specify what run status a `blocked` agent
result maps to (presumably `needs_review`, but this is unspecified). If backend implements
it one way and autotester tests another, this is a production bug waiting to happen.

**Required action**:
1. In the list/detail response examples, rename the nested field to `result.agent_status`
   OR add a callout box explicitly distinguishing run status from agent-reported status.
2. Document the mapping: `AgentResult.status = "blocked"` → `agent_runs.status = "needs_review"`.
3. State this mapping in the `[RESULT]` Block Parse Contract table.

---

### DX-002 — `raw_output` nullability in list response is ambiguous

**Location**: `GET /api/v1/runs` response example  
**Problem**: The response example shows `"raw_output": null` but the note below says it is
"omitted from list responses for size reasons." These are two different behaviors: `null`
means the field is present with no value; "omitted" means the field is absent from the
serialized JSON. Pydantic's `Optional[str]` with default serialization will include
`"raw_output": null` — but the intent appears to be exclusion. If a client SDK auto-generates
from the schema, it will expect the field and fail when it is absent, or vice versa.

**Required action**: Pick one behavior and document it explicitly:
- Option A (recommended): Field is always present; list responses return `null`, detail
  responses return the actual value. Simpler for clients.
- Option B: Field is excluded from list serialization entirely using `model_config` with
  `exclude_unset=True` or a separate list schema. Document this in the schema definition.

---

### DX-003 — `status` filter valid values undocumented

**Location**: `GET /api/v1/runs` query parameters table  
**Problem**: `status` is typed as `string` with no documented valid values. An operator
trying to filter by `timed_out` or `needs_review` has no indication these are the valid
tokens. Typos (e.g. `"timeout"` instead of `"timed_out"`) will silently return an empty
list rather than a 422 validation error unless constrained at the API layer.

**Required action**: Add a `Valid values` column to the query parameter table:

| Parameter | Type | Default | Valid values | Description |
|-----------|------|---------|--------------|-------------|
| `status` | string | — | `pending`, `running`, `completed`, `needs_review`, `failed`, `timed_out` | Filter by run status |

Also document whether an invalid value returns 422 or silently returns empty results.

---

### DX-004 — Max `limit` inconsistency with other services

**Location**: `GET /api/v1/runs` query parameter table  
**Problem**: The contract sets `limit` max at 200. The orchestrator's `GET /api/v1/jobs`
uses max 100. No other service in the monorepo uses 200 as the ceiling. Operators and
tooling that work across services will hit an inconsistency and may make incorrect
assumptions about safe page sizes.

**Required action**: Align to 100 (monorepo convention) unless there is a documented reason
for 200. If 200 is intentional (e.g. log-dump use case), add a comment explaining why.

---

### DX-005 — `runner_mode` valid values undocumented in response schema

**Location**: `AgentRunResponse` schema, `GET /api/v1/runs` response example  
**Problem**: `runner_mode: str` in the response schema has no documented valid values.
The health endpoint example reveals `"claude_code"`, and the spec mentions `api` mode, but
the API contract itself never states these as the only two values. Any client code doing
`if run.runner_mode == "claude_code"` is writing against an undocumented assumption.

**Required action**: Change the type annotation to `Literal["claude_code", "api"]` in the
schema definition and add a `Valid values: claude_code, api` note in the contract.

---

## Non-Blocking Suggestions

### DX-006 — List response missing pagination echo

**Current**: `{"items": [...], "total": N}`  
**Suggestion**: Add `offset` and `limit` to the response body:
```json
{"items": [...], "total": N, "offset": 0, "limit": 50}
```
This is already the convention in the ticket-manager admin list endpoint. It allows clients
to build pagination UI without tracking request state separately. Not required to match
other dispatcher-service endpoints, but worth aligning for consistency.

---

### DX-007 — Health endpoint does not signal DB readiness

**Current**: `{"status": "ok", "runner_mode": "claude_code"}`  
**Suggestion**: Add a `db` field indicating whether the database connection pool is healthy:
```json
{"status": "ok", "runner_mode": "claude_code", "db": "ok"}
```
All other Dark Factory services that use Docker healthchecks rely on `/api/health` to gate
readiness. A service reporting `"ok"` when its DB is unreachable will pass the healthcheck
but fail on first real request. This is an operational pain point, not a blocker for Phase 3.

---

### DX-008 — Document 401 and 422 error shapes

**Current**: Only 404 error shape is documented.  
**Suggestion**: Add a section documenting standard error shapes:

| Status | When | Response body |
|--------|------|---------------|
| 401 | Missing or invalid Bearer token | `{"detail": "Not authenticated"}` |
| 422 | Invalid query parameter (e.g. bad UUID for `run_id`) | FastAPI standard validation error |
| 404 | Run not found | `{"detail": "Run not found"}` |
| 500 | Unhandled internal error | `{"detail": "Internal server error"}` |

This directly unblocks autotester's negative-path test coverage.

---

## What Is Already Good

- Status enum values are semantically clear and unambiguous for their domain
  (`needs_review` vs `failed` vs `timed_out` all mean distinct, actionable states).
- Graceful degradation behavior for outbound calls (TM comment failure doesn't block
  Orchestrator trigger) is explicitly documented — this is the right level of detail.
- The `[RESULT]` block contract table is thorough and directly testable as written.
- `AgentContext` schema field names are consistent with the markdown template sections
  they correspond to — no guessing required when reading the context builder code.
- `SERVICE_JWT` stripping requirement is documented in two places (context contract and
  field notes) — hard to miss.

---

## Recommended Review Order for Backend

Address in this sequence before committing Phase 3 implementation:

1. **DX-001** — mapping `blocked` → `needs_review` must be decided before `result_parser.py` is written
2. **DX-002** — `raw_output` serialization behavior affects the `AgentRunListResponse` schema
3. **DX-003** — constraining `status` filter affects the `GET /api/v1/runs` handler signature
4. **DX-004** — limit cap is a one-line change; do it now before tests are written against 200
5. **DX-005** — type annotation change only; no behavior change
