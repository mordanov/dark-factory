# Contract: Ticket Resource Increment

**Endpoint**: `POST /api/v1/tickets/{ticket_id}/resources`
**Auth**: JWT Bearer (any authenticated user)
**Tags**: Resources

## Request

```http
POST /api/v1/tickets/{ticket_id}/resources
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "time_spent_delta": 120,
  "tokens_consumed_delta": 500
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `time_spent_delta` | integer | no (default 0) | `>= 0` |
| `tokens_consumed_delta` | integer | no (default 0) | `>= 0` |

At least one field must be `> 0`.

## Response — 200 OK

```json
{
  "ticket_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "time_spent": 240,
  "tokens_consumed": 1500,
  "event_id": "7b2a4c81-1234-5678-abcd-ef0123456789"
}
```

## Error responses

| Status | Condition |
|---|---|
| 400 Bad Request | Both deltas are 0 (router/service check) |
| 422 Unprocessable Entity | A delta is negative (Pydantic `ge=0` field constraint) |
| 401 Unauthorized | Missing or invalid JWT |
| 404 Not Found | Ticket does not exist or is soft-deleted |

## Behaviour

1. Acquires a row lock on the ticket (`SELECT … FOR UPDATE`).
2. Applies atomic increments: `time_spent += time_spent_delta`, `tokens_consumed += tokens_consumed_delta`.
3. Emits a `ticket.resources_incremented` event with `prev_state` and `new_state`.
4. Returns the new totals and the event ID.

No assignment check is applied. Any authenticated user may increment resource counters on any ticket.
