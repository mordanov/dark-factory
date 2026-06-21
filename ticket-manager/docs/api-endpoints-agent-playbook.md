# Agent API Playbook (Ticket Manager)

This document is an API-first guide for agents and automation scripts.

## 1) Base URL and auth

- API prefix: `/api/v1`
- OpenAPI UI: `/docs`
- Health endpoints (no auth): `/health`, `/ready`
- Auth scheme: `Authorization: Bearer <access_token>`

### Login flow

`POST /api/v1/auth/login` (or `/api/v1/auth/token`, same behavior)

Request:

```json
{
  "email": "agent@example.com",
  "password": "secret123"
}
```

Response:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_token": "<refresh>"
}
```

Refresh token:
- `POST /api/v1/auth/refresh` with `{"refresh_token":"..."}`

Logout/revoke refresh token:
- `POST /api/v1/auth/logout` with `{"refresh_token":"..."}`

## 2) Roles and permissions (from backend behavior)

- Roles: `administrator`, `user`
- Admin-only endpoints: `/api/v1/admin/*`
- Most project/ticket endpoints: any authenticated user
- Ticket transition endpoint has additional RBAC: caller must be a current assignee of that ticket.

## 3) Key enums and values

### Ticket status (`TicketStatus`)
- `OPEN`
- `IN_PROGRESS`
- `IN_REVIEW`
- `DONE`
- `CLOSED`

Allowed transitions:
- `OPEN -> IN_PROGRESS`
- `IN_PROGRESS -> IN_REVIEW`
- `IN_REVIEW -> DONE` or `IN_REVIEW -> IN_PROGRESS`
- `DONE -> CLOSED` or `DONE -> IN_PROGRESS`
- `CLOSED` is terminal

### Ticket type (`TicketType`)
- `bug`, `feature`, `improvement`, `investigation`, `discovery`, `reporting`, `testing`, `analysis`, `other`

### Ticket spec (`TicketSpec`)
- `backend`, `frontend`, `architecture`, `testing`, `business_analysis`, `product_management`, `other`

## 4) Endpoint map by agent function

### A) User administration (create/edit/block/unblock users)

- List users: `GET /api/v1/admin/users`
- Create user: `POST /api/v1/admin/users`
- Edit user: `PATCH /api/v1/admin/users/{user_id}`
- Block user: `POST /api/v1/admin/users/{user_id}/block`
- Unblock user: `POST /api/v1/admin/users/{user_id}/unblock`

Create user body:

```json
{
  "email": "backend@agents.local",
  "password": "change-me-strong",
  "role": "user"
}
```

Edit user body (any subset):

```json
{
  "email": "new-email@agents.local",
  "role": "user",
  "password": "new-strong-password"
}
```

Notes:
- `password` min length is 8.
- Admin cannot edit own account via this endpoint.
- Admin cannot block own account.
- Block/unblock operations are idempotent.

### B) Projects

- Create project: `POST /api/v1/projects`
- List projects: `GET /api/v1/projects`

Create project body:

```json
{
  "name": "Q3 Delivery",
  "code": "PROJ-001"
}
```

Validation:
- `code` must match `AAAA-NNN` (4 uppercase letters, hyphen, 3 digits).
- Example valid: `ABCD-123`

### C) Tickets

- List project tickets: `GET /api/v1/projects/{project_id}/tickets`
  - Optional query: `status`, `assignee_id`, `page`, `page_size`
- Create ticket: `POST /api/v1/projects/{project_id}/tickets`
- Get ticket: `GET /api/v1/tickets/{ticket_id}`
- Update ticket: `PATCH /api/v1/tickets/{ticket_id}`
- Delete (soft delete): `DELETE /api/v1/tickets/{ticket_id}`
- Create follow-up ticket: `POST /api/v1/tickets/{ticket_id}/follow-ups`

Create ticket body:

```json
{
  "title": "Implement ticket export",
  "description": "CSV export for project board",
  "ticket_type": "feature",
  "ticket_spec": "backend",
  "urgent": false,
  "blocker": false,
  "bugfix": false,
  "tags": ["api", "export"]
}
```

Update ticket body (partial):

```json
{
  "title": "Implement ticket export v2",
  "description": "Include filters",
  "ticket_type": "improvement",
  "ticket_spec": "backend",
  "urgent": true,
  "blocker": false,
  "bugfix": false
}
```

Authorizations:
- Update/delete: ticket creator or administrator.
- Delete blocked if ticket has active follow-up tickets (`409`).

### D) Assignments

- Assign user to ticket: `POST /api/v1/tickets/{ticket_id}/assignments`
- Unassign user: `DELETE /api/v1/tickets/{ticket_id}/assignments/{user_id}`

Assign request body:

```json
{
  "user_id": "11111111-1111-1111-1111-111111111111"
}
```

Notes:
- Assign returns `409` if already assigned.
- Unassign requires ticket creator or administrator.

### E) Progress reporting (job report content)

- Submit/update progress: `PUT /api/v1/tickets/{ticket_id}/progress`
- List progress updates: `GET /api/v1/tickets/{ticket_id}/progress`

Progress body:

```json
{
  "content": "Implemented parser, added tests, opened PR #42"
}
```

Rules:
- Caller must be an active assignee to submit/update progress (`403` otherwise).
- This is one updatable progress record per `(ticket, user)`.

### F) Resource reporting (job metrics)

- Increment resource counters: `POST /api/v1/tickets/{ticket_id}/resources`

Request body:

```json
{
  "time_spent_delta": 900,
  "tokens_consumed_delta": 12000
}
```

Rules:
- Deltas must be non-negative (`>= 0`).
- At least one delta must be greater than zero.
- Endpoint is increment-only; no decrement or reset endpoint.

### G) Ticket transition

- Transition ticket status: `POST /api/v1/tickets/{ticket_id}/transitions`

Body:

```json
{
  "to_status": "IN_REVIEW"
}
```

Rules:
- Caller must be in ticket assignees (`403` otherwise).
- Transition must be allowed by workflow (`409` on invalid move).
- Every currently assigned user must have submitted progress (`422` if missing updates).

Blocked transition (`422`) shape:

```json
{
  "detail": {
    "detail": "Transition blocked: not all assignees have submitted progress updates",
    "missing_updates": [
      {
        "user_id": "...",
        "email": "frontend@agents.local"
      }
    ]
  }
}
```

### H) Ticket events and tags

- List events: `GET /api/v1/tickets/{ticket_id}/events?page=1&page_size=50`
- Search tags: `GET /api/v1/tags?q=back`
- Add tag to ticket: `POST /api/v1/tickets/{ticket_id}/tags` with `{"name":"backend"}`
- Remove tag from ticket: `DELETE /api/v1/tickets/{ticket_id}/tags/{tag_name}`

## 5) Agent-ready end-to-end sequences

### Sequence 1: bootstrap users (administrator)
1. Login as administrator.
2. `GET /api/v1/admin/users`.
3. For each missing role account: `POST /api/v1/admin/users`.
4. For existing account with wrong email/role/password: `PATCH /api/v1/admin/users/{id}`.
5. If account should be disabled: `POST /api/v1/admin/users/{id}/block`.
6. To reactivate: `POST /api/v1/admin/users/{id}/unblock`.

### Sequence 2: project + ticket creation
1. Login.
2. `POST /api/v1/projects`.
3. `POST /api/v1/projects/{project_id}/tickets` for each work item.
4. Optionally `POST /api/v1/tickets/{ticket_id}/follow-ups` for derived tasks.
5. Optionally assign users via `POST /api/v1/tickets/{ticket_id}/assignments`.

### Sequence 3: execute, report, transition
1. Assigned user submits progress via `PUT /api/v1/tickets/{ticket_id}/progress`.
2. Assigned user reports metrics via `POST /api/v1/tickets/{ticket_id}/resources`.
3. Assigned user transitions status via `POST /api/v1/tickets/{ticket_id}/transitions`.
4. If transition blocked (422), check `missing_updates`, collect remaining updates, retry.

## 6) Error handling cheat-sheet

- `400`: bad request/domain validation (duplicate admin email, 0/0 resources, etc.)
- `401`: invalid credentials/token
- `403`: permission denied (not admin, not assignee, blocked login)
- `404`: entity not found
- `409`: conflict/invalid transition/duplicate assignment
- `422`: schema validation errors or transition blocked by missing progress

## 7) Minimal cURL examples

Use these as templates.

```bash
# 1) Login
curl -sS -X POST "$API_BASE/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"email":"project-administrator@agents.local","password":"change-me"}'

# 2) Create project (replace TOKEN)
curl -sS -X POST "$API_BASE/api/v1/projects" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Agent Sprint","code":"AGNT-001"}'

# 3) Create ticket (replace PROJECT_ID)
curl -sS -X POST "$API_BASE/api/v1/projects/$PROJECT_ID/tickets" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Implement API doc","ticket_spec":"backend"}'

# 4) Submit progress (replace TICKET_ID)
curl -sS -X PUT "$API_BASE/api/v1/tickets/$TICKET_ID/progress" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"Done and tested"}'

# 5) Report resources
curl -sS -X POST "$API_BASE/api/v1/tickets/$TICKET_ID/resources" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"time_spent_delta":600,"tokens_consumed_delta":2500}'

# 6) Transition ticket
curl -sS -X POST "$API_BASE/api/v1/tickets/$TICKET_ID/transitions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_status":"IN_REVIEW"}'
```

## 8) Source of truth references

- Route wiring: `backend/src/api/v1/router.py`
- Auth + token checks: `backend/src/api/v1/auth.py`, `backend/src/core/security.py`
- Admin endpoints: `backend/src/api/v1/admin.py`
- Project/ticket endpoints: `backend/src/api/v1/projects.py`, `backend/src/api/v1/tickets.py`
- Assign/progress/transition/resource: `backend/src/api/v1/assignments.py`, `backend/src/api/v1/progress.py`, `backend/src/api/v1/transitions.py`, `backend/src/api/v1/resources.py`
- Runtime OpenAPI: `/docs`
