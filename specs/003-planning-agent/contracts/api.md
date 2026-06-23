# API Contracts: Planning Agent for Prompt Studio

**Feature**: `003-planning-agent`
**Date**: 2026-06-23
**Base URL (container internal)**: `http://user-input-manager:8000`

## Inbound API — New Planning Endpoints

All endpoints are added to `src/api/v1/planning.py` and registered with prefix `/sessions`.
All require `Authorization: Bearer <access_token>` except where noted.
Ownership is verified: the authenticated user must own the session.

---

### POST `/sessions/{session_id}/plan`

Trigger plan generation. Creates a `PromptPlan` row (status `draft`) and starts generation.

**Auth**: Bearer token (session owner)

**Path params**:
- `session_id` — UUID

**Preconditions**: session status MUST be `approved`. Returns `409` if not.

**Response `202 Accepted`**:
```json
{
  "session_id": "uuid",
  "plan_id": "uuid",
  "status": "planning"
}
```

**Error responses**:
- `404` — session not found
- `403` — not session owner
- `409` — session not in `approved` status

**Side effects**: session status → `planning`; plan row created with `status = draft`.

---

### GET `/sessions/{session_id}/plan`

Get the current plan for a session.

**Auth**: Bearer token (session owner)

**Response `200 OK`** (`PlanResponse`):
```json
{
  "id": "uuid",
  "session_id": "uuid",
  "status": "ready|confirmed|tickets_created|error",
  "plan_content": {
    "epic": { "local_id": "epic-1", "title": "...", "description": "...", "ticket_type": "epic" },
    "stories": [
      {
        "local_id": "story-1",
        "title": "...",
        "description": "...",
        "ticket_type": "story",
        "tasks": [
          {
            "local_id": "task-1-1",
            "title": "...",
            "description": "...",
            "ticket_type": "task",
            "complexity": "M",
            "depends_on": []
          }
        ]
      }
    ]
  },
  "agent_config": { "project_id": "...", "tech_stack": ["..."], "agent_overrides": [] },
  "validation_errors": null,
  "created_ticket_ids": null,
  "ticket_id_map": null,
  "tm_epic_id": null,
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

**Error responses**:
- `404` — session not found or no plan exists yet
- `403` — not session owner

---

### PUT `/sessions/{session_id}/plan`

Update plan content (user edits). Accepted only when plan `status = ready`.

**Auth**: Bearer token (session owner)

**Request body**:
```json
{
  "plan_content": { ... }
}
```

**Preconditions**: plan status MUST be `ready`. Returns `409` if not.

**Response `200 OK`**: Updated `PlanResponse`

**Validation**: Full `PlanValidator` run before save. On failure:
```json
{
  "detail": "Plan validation failed",
  "errors": ["error message 1", "error message 2"]
}
```
→ HTTP `422 Unprocessable Entity`

**Error responses**:
- `404` — session or plan not found
- `403` — not session owner
- `409` — plan not in editable state (`ready`)
- `422` — validation errors

---

### POST `/sessions/{session_id}/plan/confirm`

Confirm the plan and start background ticket creation.

**Auth**: Bearer token (session owner)

**Preconditions**: plan status MUST be `ready`. Returns `409` if not.

**Response `202 Accepted`**:
```json
{
  "session_id": "uuid",
  "plan_id": "uuid",
  "status": "confirmed"
}
```

**Side effects**:
- plan status → `confirmed`
- session status → `plan_confirmed`
- Background task: `_create_tickets(session_id)` starts asynchronously

**Error responses**:
- `404` — session or plan not found
- `403` — not session owner
- `409` — plan not in `ready` state

---

### GET `/sessions/{session_id}/plan/status`

Poll ticket creation progress.

**Auth**: Bearer token (session owner)

**Response `200 OK`** (`PlanStatusResponse`):
```json
{
  "status": "confirmed|tickets_created|error",
  "created_count": 3,
  "total": 7,
  "errors": []
}
```

`total` = 1 (epic) + len(stories) + sum(len(story.tasks) for story in stories)

**Error responses**:
- `404` — session or plan not found
- `403` — not session owner

---

## Inbound API — Removed Endpoint

### ~~POST `/sessions/{session_id}/approve`~~ REMOVED

This endpoint and its `ApproveRequest` schema are deleted. Any client calling this endpoint
will receive `404 Not Found`. Frontend must migrate to the new planning flow.

---

## Outbound Calls — Ticket Manager

All calls use the existing `TicketManagerClient` pattern (Bearer token, retry once on 401).

### `POST /api/projects/{project_id}/tickets` (via TMPlanClient)

**Create Epic** request body:
```json
{
  "title": "string",
  "description": "string",
  "type": "epic",
  "tags": []
}
```
Note: No `needs-estimation` tag (plan tickets are pre-scoped).

**Create Story** request body:
```json
{
  "title": "string",
  "description": "string",
  "type": "story",
  "tags": ["story"]
}
```

**Create Task** request body:
```json
{
  "title": "string",
  "description": "string",
  "type": "task",
  "tags": ["complexity-M"],
  "depends_on": ["tm-ticket-id-1"]
}
```
`depends_on` uses resolved TM ticket IDs from `ticket_id_map`.

**Response**: TM ticket object; `str(response["id"])` stored in `ticket_id_map`.

---

## Outbound Calls — ContextDistiller

### `POST /memory/{project_id}/agent-config`

Store agent configuration after successful ticket creation.

**Request body**: `AgentConfig` JSON
```json
{
  "project_id": "string",
  "tech_stack": ["string"],
  "agent_overrides": [
    { "agent_id": "backend", "override_text": "..." }
  ]
}
```

**Response `201 Created`**:
```json
{ "project_id": "string", "stored_at": "ISO8601" }
```

**Failure handling**: Timeout (10s), any non-2xx, or exception → log only, continue.
This call is best-effort and MUST NOT block or raise to the caller.

---

## ContextDistiller New Endpoints (context-distiller service)

These are added to `services/context-distiller/src/api/v1/memory.py`.

### `POST /memory/{project_id}/agent-config`

**Auth**: Bearer token (`UserDep`, same as existing `/memory/*`)

**Request**: `AgentConfig` JSON (described above)

**Response `201`**:
```json
{ "project_id": "string", "stored_at": "ISO8601" }
```

**Storage**: MongoDB collection `agent_configs`, upsert by `_id = project_id`.

### `GET /memory/{project_id}/agent-config`

**Auth**: Bearer token

**Response `200`**: `AgentConfig` JSON or `404` if not found.

---

## Frontend API Client Extensions (`client.ts`)

```typescript
export const planningApi = {
  trigger:   (sessionId: string) =>
               api.post<{ session_id: string; plan_id: string; status: string }>(
                 `/sessions/${sessionId}/plan`
               ),
  get:       (sessionId: string) =>
               api.get<PlanResponse>(`/sessions/${sessionId}/plan`),
  update:    (sessionId: string, content: PlanContent) =>
               api.put<PlanResponse>(`/sessions/${sessionId}/plan`, { plan_content: content }),
  confirm:   (sessionId: string) =>
               api.post<{ session_id: string; plan_id: string; status: string }>(
                 `/sessions/${sessionId}/plan/confirm`
               ),
  getStatus: (sessionId: string) =>
               api.get<PlanStatusResponse>(`/sessions/${sessionId}/plan/status`),
}
```
