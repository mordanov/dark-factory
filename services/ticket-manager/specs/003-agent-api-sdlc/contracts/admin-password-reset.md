# Contract: Admin User Update (extended with password reset)

**Endpoint**: `PATCH /api/v1/admin/users/{user_id}`
**Auth**: JWT Bearer — `administrator` role required
**Tags**: Admin

## Request (extended)

All fields optional. Unchanged fields are not modified.

```http
PATCH /api/v1/admin/users/{user_id}
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{
  "password": "new-secure-password"
}
```

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `email` | string (email) | valid email | Pre-existing field |
| `role` | `"administrator"` \| `"user"` | — | Pre-existing field |
| `password` | string | min length 8 | **New field** — triggers bcrypt re-hash |

## Response — 200 OK

Same as `AdminUserResponse` (unchanged):

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "backend@agents.local",
  "role": "user",
  "created_at": "2026-05-24T10:00:00Z",
  "blocked_at": null
}
```

## Error responses

| Status | Condition |
|---|---|
| 400 Bad Request | Password shorter than 8 characters |
| 401 Unauthorized | Missing or invalid JWT |
| 403 Forbidden | Authenticated user is not an administrator |
| 404 Not Found | User ID does not exist |

## Behaviour

When `password` is provided in the request body, `admin_service.update_user` hashes the new password with `bcrypt` and updates `user.hashed_password`. A structured log event `admin_user_password_reset` is emitted (no event in `ticket_events` — this is a user management action, not a ticket action).

## Usage by project-administrator skill

The project-administrator agent calls this endpoint when it discovers that stored credentials for an agent account are no longer valid (login returns 401). After the PATCH, it updates the local `{role}/credentials.json` with the new password.
