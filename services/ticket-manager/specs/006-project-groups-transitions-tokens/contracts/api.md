# API Contracts: Project Groups, Assignee-Only Transitions, and Tokens Spent

**Feature**: `006-project-groups-transitions-tokens` | **Date**: 2026-06-23

All new and modified endpoints follow the existing versioned prefix `/api/v1/`.
Full human-readable documentation lives in `docs/api-updates.md` (SC-007).

---

## US1 — Project Groups

### POST /api/v1/groups

Create a new project group.

**Auth**: `Bearer <token>` (any authenticated user)

**Request**:
```json
{
  "identifier": "TEAM1",
  "name": "Team Alpha",
  "description": "Projects owned by Team Alpha"
}
```

**Validation**:
- `identifier`: `.upper()` → must match `^[A-Z0-9]{4,8}$`; UNIQUE
- `name`: non-empty, ≤255 chars
- `description`: optional

**Response 201**:
```json
{
  "id": "uuid",
  "identifier": "TEAM1",
  "name": "Team Alpha",
  "description": "Projects owned by Team Alpha",
  "is_system": false,
  "created_at": "2026-06-23T10:00:00Z",
  "project_count": 0
}
```

**Errors**:
- `409 Conflict` — identifier already exists
- `422 Unprocessable` — identifier fails format validation

---

### GET /api/v1/groups

List all project groups.

**Auth**: Bearer

**Query params**: none (all groups returned; group has project_count)

**Response 200**:
```json
{
  "items": [
    { "id": "uuid", "identifier": "DEFAULT", "name": "Default", "is_system": true, "project_count": 5, ... },
    { "id": "uuid", "identifier": "TEAM1", "name": "Team Alpha", "is_system": false, "project_count": 2, ... }
  ],
  "total": 2
}
```

---

### GET /api/v1/groups/{group_id}

Get a single group by UUID.

**Response 200**: `ProjectGroupResponse` (same as create response)  
**404** if not found.

---

### PATCH /api/v1/groups/{group_id}

Update a group's `name` and/or `description`. Identifier is immutable.

**Request** (all fields optional):
```json
{ "name": "Team Beta", "description": "Renamed team" }
```

**Response 200**: updated `ProjectGroupResponse`  
**404** if not found.

---

### DELETE /api/v1/groups/{group_id}

Delete a group.

**Response 204**: No content.

**Errors**:
- `409 Conflict` — group `is_system = TRUE` (DEFAULT group undeletable)
- `409 Conflict` — group still has projects linked to it

---

### POST /api/v1/projects (MODIFIED)

**New field in request**: `group_id` (UUID, optional — defaults to DEFAULT group id if omitted).

**New field in response**: `group_id` (UUID), `group` (embedded `ProjectGroupResponse`).

**Before (existing)**:
```json
{ "name": "My Project", "code": "PROJ-001" }
```

**After (modified)**:
```json
{ "name": "My Project", "code": "PROJ-001", "group_id": "uuid-of-group" }
```

Response now includes:
```json
{
  "id": "uuid",
  "name": "My Project",
  "slug": "my-project",
  "code": "PROJ-001",
  "group_id": "uuid",
  "group": { "id": "uuid", "identifier": "DEFAULT", "name": "Default", ... },
  "created_at": "...",
  "ticket_counts": { ... }
}
```

---

### GET /api/v1/projects (MODIFIED)

**New query param**: `group_id` (UUID, optional). When provided, returns only projects in that group.

**Before**: `GET /api/v1/projects`  
**After**: `GET /api/v1/projects?group_id=<uuid>`

Response shape unchanged except each `ProjectResponse` now includes `group_id` and `group`.

---

### PATCH /api/v1/projects/{project_id} (NEW)

Update a project's group assignment (and optionally other mutable fields).

**Auth**: Bearer (administrator or project creator)

**Request**:
```json
{ "group_id": "uuid-of-new-group" }
```

**Response 200**: updated `ProjectResponse` with new group.  
**404** if project not found.  
**404** if group_id not found.

---

## US2 — Assignee-Only Transitions (No Mandatory Progress Update)

### POST /api/v1/tickets/{ticket_id}/transitions (MODIFIED)

**Change**: Progress-update gate removed. Assignee-only authorization remains.

**Before (422 error when missing progress updates)**:
```json
{
  "detail": {
    "error": "transition_blocked",
    "missing_updates": [{ "user_id": "uuid", "email": "user@example.com" }]
  }
}
```
This 422 response is **no longer returned**.

**After**: Transition succeeds immediately if the actor is an assignee and `to_status` is a valid next state. Non-assignees still receive `403 Forbidden`.

**Request** (unchanged):
```json
{ "to_status": "IN_PROGRESS" }
```

**Response 200** (unchanged): `TicketResponse` with updated `status`.

**Errors (unchanged)**:
- `403 Forbidden` — actor is not an assignee
- `404 Not Found` — ticket not found or deleted
- `422 Unprocessable` — `to_status` is not a valid transition from current status

**Removed error** (no longer returned):
- ~~`422 Unprocessable` — transition_blocked / missing progress updates~~

---

## US3 — Tokens Spent

### POST /api/v1/tickets/{ticket_id}/tokens-spent (NEW)

Increment the `tokens_spent` running total for a ticket.

**Auth**: Bearer (any authenticated user)

**Request**:
```json
{ "amount": 200 }
```

**Validation**:
- `amount`: integer, MUST be > 0 (≤0 → `422 Unprocessable`)

**Response 200**:
```json
{
  "ticket_id": "uuid",
  "tokens_spent": 700,
  "amount_added": 200,
  "event_id": "uuid"
}
```

**Effect**:
1. Increments `tickets.tokens_spent` by `amount` (atomic `UPDATE ... SET tokens_spent = tokens_spent + :amount`).
2. Creates an immutable `TicketEvent` of type `"ticket.tokens_spent_incremented"`.

**Errors**:
- `404 Not Found` — ticket not found or deleted
- `422 Unprocessable` — `amount` is 0 or negative

---

### GET /api/v1/tickets/{ticket_id} (MODIFIED)

**New field in response**: `tokens_spent: int` (alongside existing `tokens_consumed`).

```json
{
  "id": "uuid",
  ...
  "time_spent": 0,
  "tokens_consumed": 1000,
  "tokens_spent": 700,
  ...
}
```

---

## Frontend API Client

### New methods (`groupsApi`)

```typescript
interface ProjectGroupCreate {
  identifier: string;
  name: string;
  description?: string;
}

interface ProjectGroupResponse {
  id: string;
  identifier: string;
  name: string;
  description?: string;
  is_system: boolean;
  created_at: string;
  project_count: number;
}

const groupsApi = {
  list: () => axios.get<{ items: ProjectGroupResponse[]; total: number }>('/api/v1/groups'),
  create: (data: ProjectGroupCreate) => axios.post<ProjectGroupResponse>('/api/v1/groups', data),
  update: (id: string, data: Partial<Omit<ProjectGroupCreate, 'identifier'>>) =>
    axios.patch<ProjectGroupResponse>(`/api/v1/groups/${id}`, data),
  delete: (id: string) => axios.delete(`/api/v1/groups/${id}`),
};
```

### Modified `projectsApi`

```typescript
// list now accepts optional group_id filter
list: (groupId?: string) =>
  axios.get<ProjectListResponse>('/api/v1/projects', { params: groupId ? { group_id: groupId } : {} }),

// create now accepts optional group_id
create: (data: ProjectCreate & { group_id?: string }) =>
  axios.post<ProjectResponse>('/api/v1/projects', data),

// new: update group assignment
updateGroup: (projectId: string, groupId: string) =>
  axios.patch<ProjectResponse>(`/api/v1/projects/${projectId}`, { group_id: groupId }),
```

### New `tokensSpentApi`

```typescript
const tokensSpentApi = {
  increment: (ticketId: string, amount: number) =>
    axios.post<{ ticket_id: string; tokens_spent: number; amount_added: number; event_id: string }>(
      `/api/v1/tickets/${ticketId}/tokens-spent`,
      { amount }
    ),
};
```
