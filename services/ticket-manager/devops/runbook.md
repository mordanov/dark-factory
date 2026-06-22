# Runbook: Ticket Management System

## Purpose

Operational reference for on-call engineers and DevOps. Covers probe behavior,
auth lifecycle, session revocation, transition diagnosis, and log field reference.

## Ownership

DevOps / Platform team. Escalate application-layer issues to the backend team.

---

## 1. Health and Readiness Probes

### Endpoints

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `GET /health` | Liveness: process is running | `200 {"status": "ok"}` |
| `GET /ready` | Readiness: DB connection available | `200 {"status": "ready"}` |

### Kubernetes / Docker behavior

- **Liveness** (`/health`): if this fails, restart the container.
- **Readiness** (`/ready`): if this fails, remove the pod from the load-balancer
  pool but do not restart it. This typically means the database is unavailable.

### Diagnosis

If `/ready` returns non-200:

```bash
# Check Postgres connectivity from inside the backend container
docker exec -it <backend_container> \
  python -c "import asyncpg, asyncio; asyncio.run(asyncpg.connect('$DATABASE_URL'))"

# Check Postgres logs
docker logs <postgres_container> --tail 50
```

---

## 2. JWT Token Expiry and Refresh Flow

### Token lifecycle

| Token type | Lifetime | Storage |
|-----------|---------|---------|
| Access token | 30 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES=30`) | In-memory (frontend) |
| Refresh token | 7 days | `HttpOnly` cookie |

### Normal flow

1. `POST /api/v1/auth/login` → returns `access_token` (JWT) + sets `refresh_token` cookie.
2. Client includes `Authorization: Bearer <access_token>` on every request.
3. On `401 Unauthorized`, client calls `POST /api/v1/auth/refresh` to get a new
   access token using the refresh cookie.
4. On `POST /api/v1/auth/logout`, both tokens are invalidated (blocklist entry created).

### Diagnosing expired token errors

```bash
# Decode a JWT (no secret needed for inspection)
echo "<token>" | cut -d. -f2 | base64 -d 2>/dev/null | python -m json.tool

# Look for "exp" field — compare to current Unix timestamp
date +%s
```

---

## 3. Revoking All Sessions for a User

Use when a user account is compromised or an employee is offboarded.

### Step 1 — Blocklist all active tokens

```sql
-- Connect to the database
psql "$DATABASE_URL"

-- Insert a blocklist entry for the user's current token JTI
-- (obtain JTI from the decoded JWT or from the token_blocklist table)
INSERT INTO token_blocklist (jti, user_id, expires_at, created_at)
VALUES ('<jti>', '<user_uuid>', now() + interval '30 minutes', now());
```

### Step 2 — Invalidate all refresh tokens

```sql
-- Delete all refresh tokens for the user
DELETE FROM refresh_tokens WHERE user_id = '<user_uuid>';
```

### Step 3 — Verify

```bash
# Attempt a request with the old access token — should return 401
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer <old_token>" \
  http://localhost:8000/api/v1/tickets
# Expected: 401
```

### Step 4 — (Optional) Disable account

```sql
-- Prevent new logins by marking account inactive
-- (only if user.is_active column exists — check data model)
UPDATE users SET is_active = false WHERE id = '<user_uuid>';
```

---

## 4. Diagnosing Missing Status Transitions

**Symptom**: `PUT /api/v1/tickets/{id}/transitions` returns `422` with error code
`missing_progress_updates` — the status transition is blocked.

### Root cause

All assignees on the ticket must submit a progress update
(`PUT /api/v1/tickets/{id}/progress`) before any transition is permitted.

### Diagnosis

```sql
-- List all assignees for the ticket
SELECT u.email, u.id
FROM ticket_assignments ta
JOIN users u ON ta.user_id = u.id
WHERE ta.ticket_id = '<ticket_uuid>';

-- List which assignees have submitted a progress update
SELECT u.email, pu.note, pu.updated_at
FROM progress_updates pu
JOIN users u ON pu.user_id = u.id
WHERE pu.ticket_id = '<ticket_uuid>';

-- Missing = assignees - progress_update authors
SELECT u.email
FROM ticket_assignments ta
JOIN users u ON ta.user_id = u.id
WHERE ta.ticket_id = '<ticket_uuid>'
  AND ta.user_id NOT IN (
    SELECT user_id FROM progress_updates WHERE ticket_id = '<ticket_uuid>'
  );
```

### Resolution

Contact the assignees listed in the "Missing" result and ask them to submit
their progress update via `PUT /api/v1/tickets/{id}/progress`.

Alternatively, an administrator can submit on their behalf (check RBAC rules
before doing this in production).

---

## 5. Structured Log Field Reference

All logs are emitted as JSON via `structlog`. Each line is one JSON object.

### Common fields (every log line)

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO 8601 UTC | When the event occurred |
| `level` | string | `debug`, `info`, `warning`, `error`, `critical` |
| `event` | string | Human-readable message |
| `service` | string | Always `ticket-manager-api` |
| `environment` | string | Value of `ENVIRONMENT` env var |
| `request_id` | UUID | Correlation ID — set per HTTP request |

### Request-scoped fields

| Field | Type | Description |
|-------|------|-------------|
| `method` | string | HTTP method |
| `path` | string | Request path (no query string) |
| `status_code` | int | HTTP response status |
| `duration_ms` | float | Request processing time in milliseconds |
| `user_id` | UUID | Authenticated user (omitted for unauthenticated requests) |
| `user_role` | string | `administrator` or `user` |

### Domain event fields

| Field | Type | Description |
|-------|------|-------------|
| `domain_event` | string | e.g. `ticket.created`, `ticket.status_changed`, `progress.submitted` |
| `ticket_id` | UUID | Affected ticket |
| `project_id` | UUID | Containing project |
| `actor_id` | UUID | User who triggered the action |
| `from_status` | string | Previous ticket status (transitions only) |
| `to_status` | string | New ticket status (transitions only) |

### Fields intentionally excluded from logs

- `hashed_password`
- JWT payload or secret
- Raw request/response bodies on auth endpoints
- Any field named `*_secret` or `*_key`

### Searching logs

```bash
# All errors in the last hour (requires jq)
docker logs <backend_container> --since 1h | grep '"level":"error"' | jq .

# All events for a specific ticket
docker logs <backend_container> | jq 'select(.ticket_id == "<uuid>")'

# Slow requests (>500ms)
docker logs <backend_container> | jq 'select(.duration_ms > 500)'
```

---

## 6. Rate Limiting — Login Endpoint (F-02)

**Security finding**: POST /api/v1/auth/login has no application-level rate limiting.
bcrypt slows individual attempts but does not prevent distributed credential stuffing.

**Status**: Not implemented in v1. Documented as residual risk (tracked for v1.1).

### Mitigation — nginx reverse proxy rate limiting

If the backend is behind nginx, add to the server block:

```nginx
# Limit login endpoint to 10 requests/minute per IP
limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;

location /api/v1/auth/login {
    limit_req zone=login burst=5 nodelay;
    limit_req_status 429;
    proxy_pass http://backend:8000;
}
```

### Alternative — application-level (slowapi)

Add to `backend/src/main.py`:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Then on the login handler:
```python
@router.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, ...):
    ...
```

### Monitoring

Watch for repeated 401s from the same IP — indicates a brute-force attempt:

```bash
docker logs <backend_container> | jq 'select(.event == "auth.login_failed")' | \
  jq -r '.ip' | sort | uniq -c | sort -rn | head -20
```

---

## 7. Refresh Token Table Maintenance (F-09)

**Security finding**: The `refresh_tokens` table accumulates rows indefinitely.
Expired and revoked rows are never deleted. This causes unbounded table growth.

### Cleanup query

Run periodically (e.g., weekly cron job or scheduled maintenance window):

```sql
-- Delete tokens expired or revoked more than 7 days ago
DELETE FROM refresh_tokens
WHERE expires_at < now() - interval '7 days'
   OR (revoked_at IS NOT NULL AND revoked_at < now() - interval '7 days');
```

### Recommended schedule

- **Development**: on-demand
- **Production**: weekly, during low-traffic window
- **Automated option**: pg_cron extension (if available) or an external cron job

```bash
# Example cron (weekly, Sunday 2am UTC)
0 2 * * 0 psql "$DATABASE_URL" -c "DELETE FROM refresh_tokens WHERE expires_at < now() - interval '7 days' OR (revoked_at IS NOT NULL AND revoked_at < now() - interval '7 days');"
```

### Note on refresh token rotation (v1 limitation)

Refresh token rotation is not implemented in v1. A stolen refresh token remains valid
until it expires. Users should be instructed to **logout explicitly** to revoke their
session. Token rotation is tracked for v2.

---

## 8. Rollback Procedure

### Application rollback

```bash
# Re-deploy previous image tag
docker pull <registry>/ticket-manager-backend:<previous-tag>
docker compose up -d backend
```

### Database migration rollback

```bash
# Downgrade one migration step
cd backend
alembic downgrade -1

# Downgrade to a specific revision
alembic downgrade <revision_id>
```

**Warning**: Downgrading past a migration that dropped columns or tables is
destructive. Always take a database backup before applying migrations in production.

### Database backup before migration

```bash
pg_dump "$DATABASE_URL" > backup_$(date +%Y%m%d_%H%M%S).sql
```

---

## 9. Access Token 30-Minute Post-Logout Window (Known Residual Risk)

**What happens**: JWT access tokens are stateless and cannot be revoked server-side.
After `POST /auth/logout`, the refresh token is revoked in the database. However,
the JWT access token remains cryptographically valid until it expires (30 minutes max).

**Impact**: If an access token is stolen (XSS, network interception, memory dump),
the attacker can use it for up to 30 minutes even after the legitimate user logs out.

**Mitigations in place**:
- Access token lifetime is short (30 minutes) — limits the exposure window
- Frontend stores tokens in memory only (never localStorage) — reduces XSS risk
- HTTPS required — prevents network interception

**Monitoring**: Watch for requests with the same JWT `jti` claim after the corresponding
user has logged out. A token blocklist is not implemented in v1 but is tracked for v2.

**For user offboarding**:

1. Revoke all refresh tokens (prevents new access tokens from being issued):
   ```sql
   DELETE FROM refresh_tokens WHERE user_id = '<user_uuid>';
   ```
2. Optionally suspend the user account to prevent re-login:
   ```sql
   -- Only if users.is_active column exists — verify schema
   UPDATE users SET is_active = false WHERE id = '<user_uuid>';
   ```
3. **Accept the residual 30-minute window** — any in-flight access tokens will expire
   naturally. If immediate revocation is required, implement a token blocklist (v2).

---

## 10. Escalation

| Severity | On-call response time | Escalate to |
|----------|----------------------|-------------|
| P1 — service down | 15 min | Backend team + DevOps |
| P2 — degraded | 1 hour | DevOps |
| P3 — non-critical | Next business day | Team Slack channel |

## 11. Agent Credential File Security (F01)

Agent credential files (`{role}/credentials.json`) are excluded from git but require restricted filesystem permissions in production.

### Hardening credential file permissions

After the project-administrator bootstrap phase writes credential files, set permissions to owner-read-only:

```bash
# Restrict all credential files immediately after bootstrap
find . -name "credentials.json" -not -path "./.git/*" -exec chmod 600 {} \;

# Verify
ls -la */credentials.json
# Expected: -rw------- (600) for each file
```

### In Ansible / provisioning

```yaml
- name: Restrict agent credential file permissions
  file:
    path: "{{ item }}"
    mode: "0600"
  with_fileglob:
    - "{{ project_root }}/*/credentials.json"
```

### Monitoring

If a credential file has broader permissions (e.g., 644 or world-readable), it exposes agent passwords to other local users. Check periodically:

```bash
find . -name "credentials.json" ! -perm 600 -not -path "./.git/*" | grep . && echo "PERMISSIONS TOO BROAD" || echo "OK"
```

**Status**: Residual risk for v1 local dev. Must be addressed before any multi-user or production deployment.

---

## 12. Post-Incident Follow-Up

After every P1/P2 incident:

1. Write a post-mortem (timeline, root cause, impact, action items).
2. Convert action items to backlog tickets in the project tracker.
3. Update this runbook with any new failure modes discovered.

---

## 13. Orchestrator Service Account Configuration

The Workflow Orchestrator authenticates as a service account identified by email.
The `TICKET_MANAGER_SERVICE_EMAIL` env var must be set before starting the backend.

### Required environment variable

| Variable | Purpose | Example |
|----------|---------|---------|
| `TICKET_MANAGER_SERVICE_EMAIL` | Email of the orchestrator service account user | `orchestrator@service.internal` |

### Local development

Add to `backend/.env`:
```
TICKET_MANAGER_SERVICE_EMAIL=orchestrator@service.internal
```

### Docker Compose

Set in `docker-compose.yml` backend environment or via `.env` in the project root:
```yaml
TICKET_MANAGER_SERVICE_EMAIL=orchestrator@service.internal
```

### CI

Both `ci.yml` and `deploy-vps.yml` set `TICKET_MANAGER_SERVICE_EMAIL: orchestrator@ci.internal`
in every job that runs migrations or backend tests.

### Production (VPS)

Add to the `web-folders/.env` on the VPS:
```
TICKET_MANAGER_SERVICE_EMAIL=orchestrator@<your-domain>
```

### Diagnosis — 403 errors from orchestrator

If the orchestrator gets `403 Forbidden` from FSM patch/pending/audit endpoints:

```bash
# Verify the env var is set inside the running container
docker exec <backend_container> printenv TICKET_MANAGER_SERVICE_EMAIL

# Verify the orchestrator user exists with that exact email
docker exec -it <postgres_container> psql -U postgres -d ticket_manager \
  -c "SELECT id, email, role FROM users WHERE email = '<service_email>';"
```

The user must exist in the `users` table. Create it via the admin API or seed script
if missing — `require_service_account_or_admin` compares `current_user.email` against
this env var at request time.

---

## 14. Orchestrator Audit Events Table Maintenance

The `orchestrator_audit_events` table is append-only by design. Rows are never deleted
by application logic. Monitor table growth in production.

### Check table size

```sql
SELECT
  pg_size_pretty(pg_total_relation_size('orchestrator_audit_events')) AS total_size,
  count(*) AS row_count
FROM orchestrator_audit_events;
```

### Archive old events (optional)

If the table grows large, archive events older than a retention window to a separate
archive table before deleting (preserves auditability):

```sql
-- Archive events older than 90 days
CREATE TABLE IF NOT EXISTS orchestrator_audit_events_archive
  AS SELECT * FROM orchestrator_audit_events WHERE false;

INSERT INTO orchestrator_audit_events_archive
SELECT * FROM orchestrator_audit_events
WHERE timestamp < now() - interval '90 days';

-- Only delete after confirming the archive is complete
DELETE FROM orchestrator_audit_events
WHERE timestamp < now() - interval '90 days';
```

### Index health

```sql
-- Check index usage for the two orchestrator audit indexes
SELECT
  schemaname, tablename, indexname,
  idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE tablename = 'orchestrator_audit_events';
```

---

## 15. FSM State Troubleshooting

### Ticket stuck in pending state

A ticket is "pending" when `fsm_status IS DISTINCT FROM 'done'` AND
`(last_orchestrator_run IS NULL OR updated_at > last_orchestrator_run)`.

```sql
-- Find all pending tickets (what orchestrator polls for)
SELECT id, title, fsm_status, last_orchestrator_run, updated_at, blocked_reason
FROM tickets
WHERE fsm_status IS DISTINCT FROM 'done'
  AND (last_orchestrator_run IS NULL OR updated_at > last_orchestrator_run)
ORDER BY updated_at ASC;
```

### Check FSM history for a ticket

```sql
-- View full audit trail for a ticket
SELECT event, actor, from_state, to_state, details, timestamp
FROM orchestrator_audit_events
WHERE ticket_id = '<ticket_uuid>'
ORDER BY timestamp ASC;
```

### Clear a blocked gate manually (admin override)

When a ticket is blocked by a failed gate and needs to be unblocked by an admin:

```bash
# POST override via API (admin JWT required)
curl -X POST http://localhost:8000/api/v1/projects/<project_id>/tickets/<ticket_id>/override \
  -H "Authorization: Bearer <admin_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"override": true, "override_reason": "Manual admin override: <reason>"}'
```

The orchestrator clears `override: false` automatically on the next FSM PATCH after
processing the ticket.

### Diagnose orchestrator errors column

```sql
-- Tickets with recorded orchestrator errors
SELECT id, title, fsm_status, orchestrator_errors
FROM tickets
WHERE orchestrator_errors IS NOT NULL AND orchestrator_errors != 'null'::jsonb;
```

---

## 16. Database Migration Rollback — Migrations 015 and 016

Migrations 015 (FSM fields) and 016 (orchestrator audit events table) both include
full `downgrade()` paths.

### Rollback order

Migrations must be rolled back in reverse order: 016 first, then 015.

```bash
# Rollback migration 016 (drops orchestrator_audit_events table)
alembic downgrade -1

# Verify current head
alembic current

# Rollback migration 015 (drops FSM columns from tickets)
alembic downgrade -1
```

**Warning**: Rolling back 016 drops the `orchestrator_audit_events` table and all
audit records. Rolling back 015 drops all FSM columns (`fsm_status`, `blocked_reason`,
`brainstorm_round`, `assigned_agent`, `override`, `override_reason`,
`last_orchestrator_run`, `orchestrator_errors`) from the `tickets` table.

Always take a database backup before rolling back in production:

```bash
pg_dump "$DATABASE_URL" > backup_pre_rollback_$(date +%Y%m%d_%H%M%S).sql
```

### Verify rollback completed

```sql
-- After rolling back 015, FSM columns should not exist
SELECT column_name FROM information_schema.columns
WHERE table_name = 'tickets' AND column_name = 'fsm_status';
-- Expected: 0 rows

-- After rolling back 016, table should not exist
SELECT to_regclass('public.orchestrator_audit_events');
-- Expected: NULL
```
