# Ticket Manager — API Updates

This file documents all API changes introduced per feature. It is a required deliverable
for every feature that adds, modifies, or removes endpoints (SC-007).

---

## Feature 006: Project Groups, Assignee-Only Transitions, and Tokens Spent

**Branch**: `006-project-groups-transitions-tokens`  
**Date**: 2026-06-23  
**Spec**: `specs/006-project-groups-transitions-tokens/spec.md`  
**Full contracts**: `specs/006-project-groups-transitions-tokens/contracts/api.md`

### New Endpoints

#### Group Management

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/groups` | Create a new project group |
| `GET` | `/api/v1/groups` | List all groups with project counts |
| `GET` | `/api/v1/groups/{group_id}` | Get a single group by UUID |
| `PATCH` | `/api/v1/groups/{group_id}` | Update group name/description (identifier immutable) |
| `DELETE` | `/api/v1/groups/{group_id}` | Delete group (fails if system group or has projects) |

#### Tokens Spent

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/tickets/{ticket_id}/tokens-spent` | Increment tokens_spent by a positive amount |

### Modified Endpoints

#### POST /api/v1/projects

**Change**: Added optional `group_id` field to request body. Defaults to the `DEFAULT` group if omitted.

**New request field**:
```json
{ "group_id": "<uuid>" }
```

**New response fields**:
```json
{ "group_id": "<uuid>", "group": { "id": "...", "identifier": "DEFAULT", "name": "Default", ... } }
```

#### GET /api/v1/projects

**Change**: Added optional `group_id` query parameter for filtering.

**New query param**: `?group_id=<uuid>` (optional; omit to return all groups)

**Updated response**: Each `ProjectResponse` now includes `group_id` and embedded `group` object.

#### PATCH /api/v1/projects/{project_id} (NEW endpoint)

**Change**: New endpoint allowing update of a project's `group_id`.

**Request**:
```json
{ "group_id": "<uuid>" }
```

**Response 200**: Updated `ProjectResponse`.

#### GET /api/v1/tickets/{ticket_id}

**Change**: Response now includes `tokens_spent` field (integer, ≥0).

**New response field**:
```json
{ "tokens_spent": 700 }
```

Note: `tokens_consumed` (existing system-driven field) is unchanged.

### Removed/Changed Behaviour

#### POST /api/v1/tickets/{ticket_id}/transitions

**Change**: The `422 Unprocessable Entity` response for missing progress updates is **no longer returned**.

**Removed error response** (no longer possible):
```json
{
  "detail": {
    "error": "transition_blocked",
    "missing_updates": [{ "user_id": "uuid", "email": "user@example.com" }]
  }
}
```

**Remaining error responses** (unchanged):
- `403 Forbidden` — actor is not an assignee of this ticket
- `404 Not Found` — ticket not found or deleted
- `422 Unprocessable` — `to_status` is not a valid transition from current status

---

*Add future feature API changes as new H2 sections above this line.*
