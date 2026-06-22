# Quickstart: Agent API SDLC Integration

**Branch**: `003-agent-api-sdlc` | **Date**: 2026-05-24

This guide walks through verifying all three user stories end-to-end.

## Prerequisites

- Backend running locally: `cd backend && uvicorn src.main:app --reload`
- Database migrated: `cd backend && alembic upgrade head`
- Admin account exists (created by seed or previous setup)

---

## Story 1: Ticket Resource Tracking

### Step 1 — Authenticate as any user

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"adminpass"}' | jq .access_token
```

Save as `TOKEN`.

### Step 2 — Create a project and ticket

```bash
# Create project
PROJECT_ID=$(curl -s -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo","code":"DEMO"}' | jq -r .id)

# Create ticket
TICKET_ID=$(curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/tickets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test resource tracking","ticket_type":"feature","ticket_spec":"backend"}' \
  | jq -r .id)
```

### Step 3 — Increment resource counters

```bash
curl -s -X POST http://localhost:8000/api/v1/tickets/$TICKET_ID/resources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"time_spent_delta": 120, "tokens_consumed_delta": 500}' | jq .
```

**Expected response:**
```json
{
  "ticket_id": "<uuid>",
  "time_spent": 120,
  "tokens_consumed": 500,
  "event_id": "<uuid>"
}
```

### Step 4 — Verify journal entry

```bash
curl -s http://localhost:8000/api/v1/tickets/$TICKET_ID/events \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | select(.event_type == "ticket.resources_incremented")'
```

**Expected**: one event with `new_state.time_spent_delta = 120`.

### Step 5 — Verify decrement rejected

```bash
curl -s -X POST http://localhost:8000/api/v1/tickets/$TICKET_ID/resources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"time_spent_delta": -10, "tokens_consumed_delta": 0}' | jq .status_code
```

**Expected**: HTTP 400.

---

## Story 2: Agent User Bootstrapping

### Step 1 — Create project-administrator credential file

```bash
mkdir -p project-administrator
cat > project-administrator/credentials.json << 'EOF'
{
  "username": "admin@example.com",
  "password": "adminpass"
}
EOF
```

### Step 2 — Run project-administrator bootstrap (manual simulation)

```bash
# Authenticate as admin
ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"adminpass"}' | jq -r .access_token)

# Create product-manager agent user
curl -s -X POST http://localhost:8000/api/v1/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"product-manager@agents.local","password":"agentpass123","role":"user"}' | jq .

# Write credentials file
mkdir -p product-manager
echo '{"username":"product-manager@agents.local","password":"agentpass123"}' \
  > product-manager/credentials.json
```

### Step 3 — Verify agent can authenticate

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"product-manager@agents.local","password":"agentpass123"}' | jq .access_token
```

**Expected**: valid JWT token string.

### Step 4 — Verify credentials.json excluded from git

```bash
git status product-manager/credentials.json
```

**Expected**: file not listed (excluded by `.gitignore`).

### Step 5 — Test password reset (wrong password scenario)

```bash
# Get user ID
USER_ID=$(curl -s http://localhost:8000/api/v1/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | jq -r '.items[] | select(.email == "product-manager@agents.local") | .id')

# Reset password
curl -s -X PATCH http://localhost:8000/api/v1/admin/users/$USER_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"password":"newpass456"}' | jq .email

# Verify old password rejected
curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"product-manager@agents.local","password":"agentpass123"}' | jq .detail
```

**Expected**: "agentpass123" returns 401 detail; "newpass456" returns a valid token.

---

## Story 3: Agent Ticket Lifecycle via API

### Step 1 — Authenticate as product-manager agent

```bash
PM_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"product-manager@agents.local","password":"agentpass123"}' | jq -r .access_token)
```

### Step 2 — Create a ticket with tags and assign to backend agent

```bash
# Get backend user ID (or use product-manager as assignee for demo)
BACKEND_USER_ID=$(curl -s http://localhost:8000/api/v1/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | jq -r '.items[] | select(.email == "backend@agents.local") | .id')

TICKET_ID=$(curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/tickets \
  -H "Authorization: Bearer $PM_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"Implement resource endpoint\",\"ticket_type\":\"feature\",\"ticket_spec\":\"backend\",\"tags\":[\"backend\",\"api\"]}" \
  | jq -r .id)

# Assign to backend agent
curl -s -X POST http://localhost:8000/api/v1/tickets/$TICKET_ID/assignments \
  -H "Authorization: Bearer $PM_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$BACKEND_USER_ID\"}" | jq .
```

### Step 3 — Transition blocked for non-assignee

```bash
# Try to transition as product-manager (not an assignee)
curl -s -X POST http://localhost:8000/api/v1/tickets/$TICKET_ID/transitions \
  -H "Authorization: Bearer $PM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_status":"IN_PROGRESS"}' | jq .detail
```

**Expected**: HTTP 403 `"Only assignees may transition this ticket"`.

### Step 4 — Backend agent submits update and transitions

```bash
BACKEND_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"backend@agents.local","password":"backendpass123"}' | jq -r .access_token)

# Submit progress update
curl -s -X PUT http://localhost:8000/api/v1/tickets/$TICKET_ID/progress \
  -H "Authorization: Bearer $BACKEND_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"Analyzed requirements. Starting implementation."}' | jq .

# Transition to IN_PROGRESS
curl -s -X POST http://localhost:8000/api/v1/tickets/$TICKET_ID/transitions \
  -H "Authorization: Bearer $BACKEND_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_status":"IN_PROGRESS"}' | jq .status
```

**Expected**: `"IN_PROGRESS"`.

### Step 5 — Transition without progress blocked

```bash
# Attempt to transition IN_REVIEW without submitting new progress
# (Add another assignee who hasn't submitted a progress update)
NEW_USER_ID="..."  # second assignee
curl -s -X POST http://localhost:8000/api/v1/tickets/$TICKET_ID/assignments \
  -H "Authorization: Bearer $BACKEND_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$NEW_USER_ID\"}" | jq .

# Submit progress for backend user only
curl -s -X PUT http://localhost:8000/api/v1/tickets/$TICKET_ID/progress \
  -H "Authorization: Bearer $BACKEND_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"Done."}' | jq .

# Try transition (new assignee hasn't submitted update)
curl -s -X POST http://localhost:8000/api/v1/tickets/$TICKET_ID/transitions \
  -H "Authorization: Bearer $BACKEND_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to_status":"IN_REVIEW"}' | jq .status_code
```

**Expected**: HTTP 422 (progress gate).

### Step 6 — Increment resources after completing work

```bash
curl -s -X POST http://localhost:8000/api/v1/tickets/$TICKET_ID/resources \
  -H "Authorization: Bearer $BACKEND_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"time_spent_delta": 3600, "tokens_consumed_delta": 4200}' | jq .
```

**Expected**: `time_spent = 3600 + any prior increments`, journal entry created.
