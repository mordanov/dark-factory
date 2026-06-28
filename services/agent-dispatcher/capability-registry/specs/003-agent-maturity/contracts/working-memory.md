# Contract: Working Memory API

**Service**: `agent-dispatcher`  
**Base path**: `/api/v1/working-memory`  
**Auth**: Keycloak service token (agents write; Orchestrator reads)

---

## GET /api/v1/working-memory/{ticket_id}

Read all working memory entries for a ticket. Called by the Orchestrator at each FSM gate.

**Path params**: `ticket_id` — the ticket identifier string

**Query params**:
- `author_role_id` (optional): filter to entries written by a specific role
- `entry_type` (optional): filter by type (`observation`, `decision`, `artifact_ref`, `question`, `answer`)
- `since` (optional): ISO 8601 timestamp — return only entries after this time
- `limit` (optional): max entries to return (default: 100, max: 500)

**Response 200**:
```json
{
  "ticket_id": "TICKET-123",
  "entries": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440010",
      "author_role_id": "backend",
      "entry_type": "observation",
      "content": "The existing authentication module uses JWT tokens with 1-hour expiry...",
      "tags": ["authentication", "security"],
      "created_at": "2026-06-28T12:05:00Z",
      "run_id": "550e8400-e29b-41d4-a716-446655440001"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440011",
      "author_role_id": "software-architect",
      "entry_type": "decision",
      "content": "We will use row-level security for tenant isolation, per security-architect consultation.",
      "tags": ["architecture", "database"],
      "created_at": "2026-06-28T12:10:00Z",
      "run_id": "550e8400-e29b-41d4-a716-446655440002"
    }
  ],
  "total": 2,
  "has_more": false
}
```

**Response 200 (empty)**: `{"ticket_id": "TICKET-123", "entries": [], "total": 0, "has_more": false}`  
**Response 401**: Missing or invalid service token

---

## POST /api/v1/working-memory/{ticket_id}

Append a new entry to working memory for a ticket. Called by an executing agent.

**Path params**: `ticket_id` — the ticket identifier string

**Request**:
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440001",
  "author_role_id": "backend",
  "entry_type": "observation",
  "content": "The existing authentication module uses JWT tokens with 1-hour expiry. No refresh mechanism is implemented.",
  "tags": ["authentication", "existing-code"]
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `run_id` | UUID | Yes | Must reference a known `agent_runs.id` |
| `author_role_id` | string | Yes | Must match a canonical role ID |
| `entry_type` | string | Yes | `observation`, `decision`, `artifact_ref`, `question`, `answer` |
| `content` | string | Yes | Entry body; max 65,536 characters |
| `tags` | `list[string]` | No | Optional keyword tags |

**Response 201**:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440012",
  "ticket_id": "TICKET-123",
  "author_role_id": "backend",
  "entry_type": "observation",
  "created_at": "2026-06-28T12:05:00Z",
  "expires_at": "2026-07-28T12:05:00Z"
}
```

**Response 400**: Invalid `entry_type`, content too long, or unknown `author_role_id`  
**Response 401**: Missing or invalid service token  
**Response 404**: `run_id` not found

---

## Cross-Ticket Isolation

The API enforces that `run_id` belongs to `ticket_id` — an agent may not write working memory for a ticket it is not executing. Attempted cross-ticket writes return 403.

---

## Error Response Shape

```json
{
  "detail": "content exceeds maximum length of 65536 characters"
}
```
