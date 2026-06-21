# Contract: Ticket Transition (updated RBAC)

**Endpoint**: `POST /api/v1/tickets/{ticket_id}/transitions`
**Auth**: JWT Bearer — actor must be an assignee of the ticket
**Tags**: Transitions

## Request (unchanged)

```http
POST /api/v1/tickets/{ticket_id}/transitions
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "to_status": "IN_PROGRESS"
}
```

Valid `to_status` values (see `workflow_service.WORKFLOW_TRANSITIONS` for allowed paths):

| From | Allowed To |
|---|---|
| `OPEN` | `IN_PROGRESS` |
| `IN_PROGRESS` | `IN_REVIEW` |
| `IN_REVIEW` | `DONE`, `IN_PROGRESS` |
| `DONE` | `CLOSED`, `IN_PROGRESS` |
| `CLOSED` | *(none — terminal state)* |

## Response — 200 OK

Full `TicketResponse` (unchanged shape, now includes `time_spent` and `tokens_consumed`).

## Error responses (updated)

| Status | Condition |
|---|---|
| 401 Unauthorized | Missing or invalid JWT |
| 403 Forbidden | **NEW** — Actor is not an assignee of this ticket (applies to all roles, including administrator) |
| 404 Not Found | Ticket does not exist or is soft-deleted |
| 409 Conflict | `to_status` is not an allowed transition from the current status |
| 422 Unprocessable Entity | Progress gate blocked: one or more assignees have not submitted a progress update |

## Behaviour change

**New check** (inserted after loading assignments, before `validate_transition`):

```python
assignee_ids = {a.user_id for a in all_assignments}
if actor.id not in assignee_ids:
    raise HTTPException(status_code=403, detail="Only assignees may transition this ticket")
```

This applies to **all roles** including `administrator`. The project-administrator agent may only transition tickets it is explicitly assigned to.

## Pre-transition workflow for agents

Before calling this endpoint, an agent must have submitted a progress update:

```http
PUT /api/v1/tickets/{ticket_id}/progress
Authorization: Bearer <access_token>
Content-Type: application/json

{ "content": "Completed implementation of the resource increment endpoint." }
```

The transition will be blocked (HTTP 422) until all assignees have submitted at least one progress update.
