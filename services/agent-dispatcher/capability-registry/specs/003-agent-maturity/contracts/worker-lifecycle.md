# Contract: Worker Lifecycle API

**Service**: `agent-dispatcher`  
**Base path**: `/api/v1/workers`  
**Auth**: Keycloak service token (all endpoints)

---

## POST /api/v1/workers/register

Register a logical worker record on agent startup.

**Request**:
```json
{
  "role_id": "backend",
  "version": "1.2.3",
  "capabilities_snapshot": {
    "python_backend": 95,
    "fastapi": 90
  }
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `role_id` | string | Yes | Must match a canonical role ID in the YAML registry |
| `version` | string | Yes | Agent image or code version string |
| `capabilities_snapshot` | object | No | `{skill: confidence}` — defaults to registry definition |

**Response 201**:
```json
{
  "worker_id": "550e8400-e29b-41d4-a716-446655440000",
  "role_id": "backend",
  "status": "idle",
  "registered_at": "2026-06-28T12:00:00Z"
}
```

**Response 400**: `role_id` not in registry  
**Response 401**: Missing or invalid service token  
**Response 409**: Existing idle/busy worker with the same `role_id` and `run_id` already registered (idempotent retry safe if `worker_id` matches)

---

## POST /api/v1/workers/{role_id}/heartbeat

Send a liveness signal for a registered worker.

**Path params**: `role_id` — canonical role ID

**Request**:
```json
{
  "worker_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "busy"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `worker_id` | UUID | Yes | ID from the registration response |
| `status` | string | No | Current status: `idle`, `busy`, `draining` |

**Response 200**:
```json
{
  "acknowledged": true,
  "next_heartbeat_deadline": "2026-06-28T12:02:00Z"
}
```

**Response 404**: `worker_id` not found or already offline  
**Response 401**: Missing or invalid service token

---

## POST /api/v1/workers/{role_id}/drain

Signal graceful shutdown for a worker.

**Path params**: `role_id` — canonical role ID

**Request**:
```json
{
  "worker_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response 200**:
```json
{
  "worker_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "draining",
  "offline_at": null
}
```

**Response 404**: Worker not found  
**Response 401**: Missing or invalid service token

---

## GET /api/v1/workers

List all registered workers with their current status.

**Query params**:
- `status` (optional): filter by status (`idle`, `busy`, `draining`, `offline`)
- `role_id` (optional): filter by role

**Response 200**:
```json
{
  "workers": [
    {
      "worker_id": "550e8400-e29b-41d4-a716-446655440000",
      "role_id": "backend",
      "status": "idle",
      "version": "1.2.3",
      "last_heartbeat_at": "2026-06-28T12:00:30Z",
      "registered_at": "2026-06-28T11:00:00Z"
    }
  ],
  "total": 1
}
```

**Response 401**: Missing or invalid service token

---

## Liveness Sweep (Internal)

`agent-dispatcher` background task runs every 60 seconds. Any worker whose `last_heartbeat_at` is older than `2 × heartbeat_interval` (default: 2 minutes) is marked `offline` and an `offline_liveness` lifecycle event is written.

This is not a client-callable endpoint.

---

## Error Response Shape (All Endpoints)

```json
{
  "detail": "role_id 'unknown-role' not found in capability registry"
}
```
