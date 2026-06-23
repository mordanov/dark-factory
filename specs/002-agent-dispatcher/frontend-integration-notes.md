# Agent Dispatcher — Frontend Client Integration Notes

**Feature**: `002-agent-dispatcher`
**Service internal URL**: `http://agent-dispatcher:8000` (container listens on 8000)
**Service dev URL**: `http://localhost:8006` (host port override in docker-compose.override.yml)
**Auth**: Bearer JWT — same `JWT_SECRET_KEY` as all other Dark Factory services

---

## Quick Start

```typescript
const BASE_URL = process.env.AGENT_DISPATCHER_URL ?? 'http://localhost:8006';

async function fetchRuns(
  token: string,
  filters: RunFilters = {}
): Promise<AgentRunListResponse> {
  const params = new URLSearchParams();
  if (filters.ticketId) params.set('ticket_id', filters.ticketId);
  if (filters.status)   params.set('status', filters.status);
  if (filters.offset)   params.set('offset', String(filters.offset));
  if (filters.limit)    params.set('limit', String(filters.limit));

  const res = await fetch(`${BASE_URL}/api/v1/runs?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`GET /api/v1/runs → ${res.status}`);
  return res.json();
}
```

---

## TypeScript Type Definitions

> **⚠️ Status enum note (DX-001)**: `AgentRun.status` and `AgentRun.result.status` are
> **different enums** despite the same field name. The outer `status` is the Dispatcher's
> run lifecycle state (6 values). The nested `result.status` is the agent's self-reported
> outcome (3 values, from the `[RESULT]` block). Keep them separate in client code.
> `result.status === 'blocked'` maps to `status === 'needs_review'` at the DB level.

```typescript
/**
 * Lifecycle state managed by the Dispatcher for a run record.
 * Distinct from AgentReportedStatus — do NOT conflate the two.
 */
export type AgentRunStatus =
  | 'pending'      // record created, agent not yet started
  | 'running'      // agent subprocess or API call is active
  | 'completed'    // agent exited cleanly with a valid [RESULT] block
  | 'needs_review' // [RESULT] missing/unparseable OR agent reported 'blocked'
  | 'failed'       // non-zero exit, subprocess error, or missing prompt file
  | 'timed_out';   // agent exceeded its configured timeout

/**
 * Agent's self-reported outcome from the [RESULT] block.
 * Distinct from AgentRunStatus — 'blocked' maps to 'needs_review' in agent_runs.
 */
export type AgentReportedStatus = 'completed' | 'needs_review' | 'blocked';

/** Runner backend used for this run. */
export type AgentRunnerMode = 'claude_code' | 'api';

/** Parsed content from the agent's [RESULT] block. null until run completes. */
export interface AgentResult {
  status: AgentReportedStatus;
  summary: string;
  artifacts: string[];
  tm_comment: string;
  brainstorm_consensus: 'agreed' | 'disagreed' | null;
  errors: string[];
}

/** A single agent run record. */
export interface AgentRun {
  id: string;               // UUID
  ticket_id: string;
  project_id: string;
  agent_id: string;
  runner_mode: AgentRunnerMode;
  status: AgentRunStatus;
  round_number: number;     // 1-indexed; always 1 for non-brainstorm runs
  brainstorm_session_id: string | null;
  /**
   * Always present in the response; null in list responses, populated in
   * single-run GET. Truncated to 64 KB. Contains no secrets.
   */
  raw_output: string | null;
  result: AgentResult | null; // null until run completes
  error_message: string | null;
  started_at: string | null;  // ISO 8601
  finished_at: string | null; // ISO 8601
  created_at: string;         // ISO 8601
}

/** Paginated list response from GET /api/v1/runs. */
export interface AgentRunListResponse {
  items: AgentRun[];
  total: number;
  /** Added in Phase 6 polish — treat as optional until confirmed present. */
  offset?: number;
  limit?: number;
}

/** Extended health response after Phase 6 polish (db field added). */
export interface HealthResponseV2 extends HealthResponse {
  db?: 'ok' | 'error'; // added in Phase 6; optional for forward-compat
}

/** Health check response from GET /api/health (no auth required). */
export interface HealthResponse {
  status: 'ok';
  runner_mode: AgentRunnerMode;
}

/** Query filters for GET /api/v1/runs. */
export interface RunFilters {
  ticketId?: string;
  /** Must be an exact AgentRunStatus value. Invalid values return 422. */
  status?: AgentRunStatus;
  offset?: number;
  limit?: number; // default 50, max 100
}
```

> **Confirmed contract resolutions** (PM decisions 2026-06-22):
> - **DX-002 confirmed**: `raw_output` is always present in list responses as `null` (not
>   omitted). Detail responses include the actual value. Type definitions above are correct.
> - **DX-004 confirmed**: `limit` max is **100** (monorepo convention).
> - **DX-007 confirmed**: Health endpoint will gain a `db` field in Phase 6 polish.
>   Treat `db` as optional in client code so early-phase builds remain compatible:
>   `health.db === 'ok'` is safe only after Phase 6 is complete.
> - **DX-006 confirmed**: List response will add `offset` and `limit` echo fields.
>   Treat them as optional until backend Phase 3 ships.

---

## Endpoints

### `GET /api/health` — no auth required

Returns service health and active runner mode. Use for readiness checks before issuing
authenticated calls. Never cached client-side; callers should re-check on reconnect.

```typescript
const health = await fetch(`${BASE_URL}/api/health`).then(r => r.json()) as HealthResponse;
// { status: 'ok', runner_mode: 'claude_code' }
```

---

### `GET /api/v1/runs` — Bearer auth required

Returns a paginated list of agent runs across all tickets. `raw_output` is **omitted**
from list items for size reasons; fetch the individual run to get it.

**Query parameters**:

| Parameter  | Type   | Default | Valid values / Max | Notes |
|------------|--------|---------|--------------------|-------|
| `ticket_id`| string | —       | any ticket ID | Filter to a specific ticket |
| `status`   | string | —       | `pending` `running` `completed` `needs_review` `failed` `timed_out` | Invalid values return 422 |
| `offset`   | int    | 0       | ≥ 0 | Pagination cursor |
| `limit`    | int    | 50      | max 100 | Page size |

**Pagination pattern**:

```typescript
async function* paginateRuns(
  token: string,
  filters: Omit<RunFilters, 'offset' | 'limit'> = {}
): AsyncGenerator<AgentRun> {
  const limit = 50;
  let offset = 0;
  while (true) {
    const page = await fetchRuns(token, { ...filters, offset, limit });
    yield* page.items;
    if (offset + limit >= page.total) break;
    offset += limit;
  }
}
```

**Example — all completed runs for a ticket**:

```typescript
const page = await fetchRuns(token, {
  ticketId: 'TKT-001',
  status: 'completed',
});
// page.items → AgentRun[]
// page.total → total matching count (may be > items.length)
```

---

### `GET /api/v1/runs/{run_id}` — Bearer auth required

Returns a single run with `raw_output` populated. Use when you need the agent's full
stdout (debugging, auditing, manual review of `needs_review` cases).

```typescript
async function fetchRun(token: string, runId: string): Promise<AgentRun> {
  const res = await fetch(`${BASE_URL}/api/v1/runs/${runId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 404) throw new Error('Run not found');
  if (!res.ok) throw new Error(`GET /api/v1/runs/${runId} → ${res.status}`);
  return res.json();
}
```

**404 shape**:

```json
{ "detail": "Run not found" }
```

---

## Status Semantics for UI Display

| Status         | Terminal? | User-facing label suggestion  | Color hint |
|----------------|-----------|-------------------------------|------------|
| `pending`      | No        | Queued                        | grey       |
| `running`      | No        | In progress                   | blue       |
| `completed`    | Yes ✅    | Done                          | green      |
| `needs_review` | Yes ⚠️    | Needs review                  | yellow     |
| `failed`       | Yes ❌    | Failed                        | red        |
| `timed_out`    | Yes ❌    | Timed out                     | orange     |

`needs_review` means the agent ran to completion but its output was not parseable as a
structured `[RESULT]` block. The `raw_output` field on the individual run record holds up
to 64 KB of the agent's raw stdout — useful for displaying in a "view logs" panel.

---

## Authentication

All `/api/v1/*` endpoints require a Bearer JWT. Use the same token issued by any other
Dark Factory service; all services share `JWT_SECRET_KEY`.

```typescript
const res = await fetch(`${BASE_URL}/api/v1/runs`, {
  headers: { Authorization: `Bearer ${yourJwt}` },
});
```

**401 shape** (standard FastAPI):

```json
{ "detail": "Not authenticated" }
```

**Token refresh**: The dispatcher validates JWTs locally with the shared secret. No
separate token exchange is needed. Refresh using the same auth flow as other services.

---

## Pagination Notes

- Default page size is 50, maximum is 100 (`limit=100`). The implementation currently accepts up to 200 but 100 is the documented contract per DX-004; treat 100 as the safe upper bound.
- `total` reflects the total matching record count, not the current page size.
- Filter by `ticket_id` to scope history to a single ticket before paginating.
- Runs are ordered by `created_at DESC` (newest first). No sort override is supported
  in v1.

---

## Brainstorm Run Fields

For runs that are part of a multi-agent architecture-review session:

- `round_number` is 1-indexed. All agents in the same round share the same
  `round_number` value.
- `brainstorm_session_id` links to the session. Multiple runs share the same session ID.
- Filter by `ticket_id` to retrieve all runs in a brainstorm session, then group by
  `round_number` and sort by `created_at` to reconstruct the session timeline.

```typescript
// Reconstruct brainstorm session timeline for a ticket
const allRuns = await fetchRuns(token, { ticketId: 'TKT-001' });
const sessionRuns = allRuns.items.filter(r => r.brainstorm_session_id !== null);
const byRound = Map.groupBy(sessionRuns, r => r.round_number);
```

---

## Error Handling Checklist

- `401`: token missing or expired — re-authenticate.
- `404` on `/api/v1/runs/{id}`: run does not exist — show "not found" message.
- `5xx`: service may be recovering; retry with exponential backoff.
- Network timeout: the health endpoint (`/api/health`) has no auth — use it for
  connectivity checks before falling back to a cached state.
- `needs_review` / `failed` / `timed_out` runs always have a TM comment posted to
  the originating ticket — do not surface `raw_output` in primary UI; offer it as
  an expandable "View raw output" action for operators.
