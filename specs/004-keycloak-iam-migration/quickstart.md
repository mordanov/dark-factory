# Quickstart & Validation Scenarios: Keycloak IAM Migration

**Feature**: 004-keycloak-iam-migration
**Date**: 2026-06-24

---

## Prerequisites

```bash
# 1. Copy and fill .env
cp infra/.env.example infra/.env
# Required fills: KC_BOOTSTRAP_ADMIN_PASSWORD, KC_DB_PASSWORD, OAUTH2_PROXY_CLIENT_SECRET,
#   OAUTH2_PROXY_COOKIE_SECRET, all KC_*_CLIENT_SECRET values, POSTGRES_PASSWORD

# 2. Build and start (first boot takes ~2min for Keycloak realm import)
docker compose -f infra/docker-compose.yml up --build -d

# 3. Wait for Keycloak to be ready
until curl -sf http://localhost:8080/realms/dark-factory > /dev/null; do
  echo "Waiting for Keycloak..."; sleep 5
done
echo "Keycloak ready"

# 4. Wait for all services to be healthy
docker compose -f infra/docker-compose.yml ps  # all should show "healthy" or "running"
```

---

## Scenario 1: Frontend Login via Keycloak SSO

**Goal**: Validate US1 — user logs in via Keycloak, gets access to both frontends.

### Setup: Create a test user in Keycloak Admin Console
```
1. Open http://localhost:8080/admin
2. Log in with KC_BOOTSTRAP_ADMIN_USERNAME + KC_BOOTSTRAP_ADMIN_PASSWORD
3. Select realm "dark-factory"
4. Users → Add user
5. Username: testuser, Email: test@dark-factory.local, Email verified: ON → Save
6. Credentials → Set password: TestPass123! → Temporary: OFF → Save
```

### Frontend login flow
```
1. Open http://studio.dark-factory.local (or localhost:5173 in dev)
2. Browser redirects to http://localhost:8080/realms/dark-factory/protocol/openid-connect/auth
3. Enter: test@dark-factory.local / TestPass123!
4. After login: redirected back to Prompt Studio, user name displayed in sidebar
5. Open http://tickets.dark-factory.local (or localhost:5174 in dev)
6. → No login prompt; SSO session reused; Ticket Manager loads immediately
```

**Expected**: Both frontends accessible with single login. Tokens in memory only — confirm
`localStorage` has no auth keys: `localStorage.getItem('token')` → `null`.

---

## Scenario 2: API Authentication with Bearer Token

**Goal**: Validate that all `/api/` endpoints require a valid Bearer token.

### Get a token (using Keycloak direct grant — for testing only)
```bash
TOKEN=$(curl -s -X POST \
  http://localhost:8080/realms/dark-factory/protocol/openid-connect/token \
  -d "grant_type=password" \
  -d "client_id=uim-frontend" \
  -d "username=test@dark-factory.local" \
  -d "password=TestPass123!" \
  | jq -r '.access_token')

echo "Token: ${TOKEN:0:50}..."
```

### Call TM API with valid token
```bash
# List projects — should return 200
curl -s -H "Authorization: Bearer $TOKEN" \
  http://tickets.dark-factory.local/api/v1/projects | jq .

# Expected: {"items": [...], "total": 0}
```

### Call without token — expect 401 JSON
```bash
curl -s http://tickets.dark-factory.local/api/v1/projects
# Expected: {"detail":"Not authenticated","code":"TOKEN_EXPIRED_OR_INVALID"}
# (from nginx @error401 handler — NOT an HTML page)
```

### Call with expired/invalid token
```bash
curl -s -H "Authorization: Bearer garbage.token.here" \
  http://tickets.dark-factory.local/api/v1/projects
# Expected: HTTP 401 {"detail":"Not authenticated","code":"TOKEN_EXPIRED_OR_INVALID"}
```

---

## Scenario 3: Administrator Role

**Goal**: Validate US2 — admin user sees Keycloak console link; regular user does not.

### Assign administrator role to test user
```
Keycloak Admin Console → dark-factory → Users → testuser
→ Role mapping → Assign role → administrator
```

### Verify in frontend
```
Refresh Prompt Studio (or log out and back in)
Sidebar → "Keycloak Admin Console" link visible
Click → opens http://localhost:8080/admin/dark-factory/console in new tab

Create a second user (testuser2) WITHOUT administrator role
Log in as testuser2 → sidebar has NO "Keycloak Admin Console" link
```

---

## Scenario 4: Service-to-Service Authentication

**Goal**: Validate US3 — Orchestrator calls TM using Client Credentials.

### Get a service token (Client Credentials)
```bash
SVC_TOKEN=$(curl -s -X POST \
  http://localhost:8080/realms/dark-factory/protocol/openid-connect/token \
  -d "grant_type=client_credentials" \
  -d "client_id=orchestrator" \
  -d "client_secret=${KC_ORCHESTRATOR_CLIENT_SECRET}" \
  | jq -r '.access_token')

echo "Service token: ${SVC_TOKEN:0:50}..."
```

### Verify service token works with TM API
```bash
# Create a project using the orchestrator service token
curl -s -X POST \
  -H "Authorization: Bearer $SVC_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Project via Service Token"}' \
  http://tickets.dark-factory.local/api/v1/projects
# Expected: {"id": "...", "name": "Test Project via Service Token", ...}
```

### Verify token cached in service (check service logs)
```bash
# First call should log JWKS fetch
docker logs dark-factory-orchestrator-1 2>&1 | grep -i "jwks"
# Subsequent calls should NOT show JWKS fetch (cached 300s)
```

---

## Scenario 5: Agent Token Injection

**Goal**: Validate that agents receive a fresh Keycloak token at spawn time.

```bash
# Check agent context generation log when a ticket is dispatched
docker logs dark-factory-agent-dispatcher-1 2>&1 | grep -i "service_token\|bearer"
# Expected: log line showing a token was injected (sub-string only, not the full token)
```

---

## Scenario 6: Data Integrity Post-Migration

**Goal**: Validate US4 — business data survives the users table removal.

```bash
# Check ticket count is preserved
TICKET_COUNT=$(curl -s \
  -H "Authorization: Bearer $TOKEN" \
  http://tickets.dark-factory.local/api/v1/projects | jq '.total')
echo "Projects: $TICKET_COUNT"

# Check no orphaned tickets (user_id column should contain valid strings)
docker exec dark-factory-postgres-1 psql -U postgres -d df_ticket_manager \
  -c "SELECT COUNT(*) FROM tickets WHERE created_by_id IS NULL;"
# Expected: 0

# Verify no users table exists
docker exec dark-factory-postgres-1 psql -U postgres -d df_ticket_manager \
  -c "\dt" | grep "users"
# Expected: (no output — table doesn't exist)
```

---

## Scenario 7: Automated Tests with AUTH_MODE=local

**Goal**: All existing tests pass without a real Keycloak instance.

```bash
# ticket-manager backend tests
cd services/ticket-manager/backend
AUTH_MODE=local TEST_JWT_SECRET=test-secret-do-not-use-in-production \
  python -m pytest tests/ -v --tb=short
# Expected: all tests pass

# user-input-manager backend tests
cd services/user-input-manager/backend
AUTH_MODE=local TEST_JWT_SECRET=test-secret-do-not-use-in-production \
  python -m pytest tests/ -v --tb=short
# Expected: all tests pass

# Frontend tests (no Keycloak needed — keycloak-js is mocked in Vitest)
cd services/ticket-manager/frontend
npm run test
# Expected: all tests pass, coverage ≥ 80%
```

---

## Scenario 8: Logout Terminates Session

```
1. Log in to Prompt Studio as testuser
2. Click "Logout" in sidebar
3. Browser redirects to Keycloak logout page, then back to Prompt Studio login page
4. Attempting to navigate to /sessions → redirected to Keycloak login again
5. Open Ticket Manager → also requires re-login (single logout propagated)
```

---

## Teardown / Reset

```bash
# To reset Keycloak realm (drops all users — USE WITH CAUTION):
docker compose -f infra/docker-compose.yml stop keycloak
docker exec dark-factory-postgres-1 psql -U postgres \
  -c "DROP DATABASE keycloak; CREATE DATABASE keycloak; GRANT ALL ON DATABASE keycloak TO keycloak_user;"
docker compose -f infra/docker-compose.yml start keycloak
# Wait for realm re-import (~60-90s)
```
