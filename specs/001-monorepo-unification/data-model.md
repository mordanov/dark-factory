# Data Model: Dark Factory Monorepo Unification

**Phase 1 output** | Branch: `001-monorepo-unification` | Date: 2026-06-22

The monorepo unification introduces no new domain entities in the application databases.
This file documents the infrastructure and configuration models — the entities that define
the system's topology and contracts.

---

## Environment Configuration Model

The `infra/.env` file is the single source of truth for all runtime configuration.
Variables are grouped into 10 sections per the constitution.

### Group 1: PostgreSQL Shared

| Variable | Required | Services | Description |
|----------|----------|----------|-------------|
| `POSTGRES_HOST` | yes | all | Hostname of the postgres container (`postgres` in compose) |
| `POSTGRES_PORT` | no (5432) | all | PostgreSQL port |
| `POSTGRES_USER` | yes | all | Superuser for init SQL |
| `POSTGRES_PASSWORD` | yes | all | Superuser password |

### Group 2: MongoDB Shared

| Variable | Required | Services | Description |
|----------|----------|----------|-------------|
| `MONGO_HOST` | yes | orchestrator, context-distiller | Hostname (`mongo` in compose) |
| `MONGO_PORT` | no (27017) | orchestrator, context-distiller | MongoDB port |

### Group 3: user-input-manager

| Variable | Required | Description |
|----------|----------|-------------|
| `UIM_DB_USER` | yes | Dedicated PG user for df_user_input |
| `UIM_DB_PASSWORD` | yes | Password for UIM PG user |
| `UIM_SECRET_KEY` | yes | JWT signing secret |
| `UIM_AUTH_MODE` | no (local) | `local` or `keycloak` |
| `UIM_TM_URL` | yes | Internal URL of ticket-manager (`http://ticket-manager:8002`) |

### Group 4: ticket-manager

| Variable | Required | Description |
|----------|----------|-------------|
| `TM_DB_USER` | yes | Dedicated PG user for df_ticket_manager |
| `TM_DB_PASSWORD` | yes | Password for TM PG user |
| `TM_SECRET_KEY` | yes | JWT signing secret |
| `TM_AUTH_MODE` | no (local) | `local` or `keycloak` |

### Group 5: orchestrator

| Variable | Required | Description |
|----------|----------|-------------|
| `ORCH_DB_USER` | yes | Dedicated PG user for df_orchestrator |
| `ORCH_DB_PASSWORD` | yes | Password for orchestrator PG user |
| `ORCH_SECRET_KEY` | yes | JWT signing secret |
| `ORCH_AUTH_MODE` | no (local) | `local` or `keycloak` |
| `ORCH_MONGO_DB` | no (df_orchestrator_docs) | MongoDB database name |

### Group 6: context-distiller

| Variable | Required | Description |
|----------|----------|-------------|
| `DISTILLER_DB_USER` | yes | Dedicated PG user for df_distiller |
| `DISTILLER_DB_PASSWORD` | yes | Password for distiller PG user |
| `DISTILLER_AUTH_MODE` | no (local) | `local` or `keycloak` |
| `DISTILLER_MONGO_DB` | no (df_distiller_docs) | MongoDB database name |

### Group 7: agent-tools

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_TOOLS_AUTH_MODE` | no (local) | `local` or `keycloak` |

### Group 8: nginx / DNS

| Variable | Required | Description |
|----------|----------|-------------|
| `UIM_HOST` | yes | DNS name for Prompt Studio (e.g. `studio.dark-factory.local`) |
| `TM_HOST` | yes | DNS name for Ticket Manager (e.g. `tickets.dark-factory.local`) |

### Group 9: auth adapter

| Variable | Required | Description |
|----------|----------|-------------|
| `KEYCLOAK_JWKS_URL` | no | Keycloak JWKS endpoint (only used when AUTH_MODE=keycloak) |

### Group 10: OpenAI / LLM

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | yes | OpenAI API key (or mock key for test env) |
| `OPENAI_BASE_URL` | no | Override for LLM endpoint (test env: http://llm-mock:11434/v1) |

---

## Auth Adapter Interface Model

Each of the five backend services implements the following interface identically.

### `AuthAdapter`

**Location**: `src/core/auth_adapter.py` (all services)

| Field / Method | Type | Description |
|----------------|------|-------------|
| `settings` | `Settings` | Injected settings object; reads `AUTH_MODE` |
| `verify(token)` | `async def verify(self, token: str) -> dict` | Returns decoded JWT claims dict or raises |

**`verify()` state machine**:

```
token → AUTH_MODE
  ├── "local"    → call existing security.verify_access_token(token) → return claims dict
  ├── "keycloak" → raise NotImplementedError("Keycloak validation not implemented")
  └── other      → raise ValueError(f"Unknown AUTH_MODE: {settings.auth_mode}")
```

**Exceptions**:
- `UnauthorizedError` (or `jose.JWTError`) — propagated from local validation; caught by
  `get_current_user` dependency and re-raised as `HTTPException(401)`
- `NotImplementedError` — Keycloak stub; caught by dependency and re-raised as
  `HTTPException(501)`
- `ValueError` — bad `AUTH_MODE`; caught at startup or first request; raises `HTTP 500`

---

## Docker Service Topology Model

### Service Registry

| Service name | Image | Internal port | Depends on | Healthcheck |
|-------------|-------|--------------|------------|-------------|
| `user-input-manager` | build: `./services/user-input-manager/backend` | 8001 | postgres (healthy) | GET /health → 200 |
| `ticket-manager` | build: `./services/ticket-manager/backend` | 8002 | postgres (healthy) | GET /health → 200 |
| `orchestrator` | build: `./services/orchestrator` | 8003 | postgres (healthy), mongo (healthy) | GET /health → 200 |
| `context-distiller` | build: `./services/context-distiller` | 8004 | postgres (healthy), mongo (healthy) | GET /health → 200 |
| `agent-tools` | build: `./services/agent-tools` | 8005 | — | GET /health → 200 |
| `postgres` | `postgres:16-alpine` | 5432 | — | `pg_isready` |
| `mongo` | `mongo:7-jammy` | 27017 | — | `mongosh ping` |
| `nginx` | build: `./infra/nginx` | 80 | user-input-manager (healthy), ticket-manager (healthy) | `wget / → 200` |

### Network Topology

```
internet → nginx:80 (network: external)
                    ↓
            ┌──────────────────────────────────┐
            │        network: internal          │
            │                                  │
            │  nginx → user-input-manager:8001  │
            │  nginx → ticket-manager:8002      │
            │  user-input-manager → orchestrator:8003    │
            │  user-input-manager → ticket-manager:8002  │
            │  orchestrator → context-distiller:8004     │
            │  all backends → postgres:5432     │
            │  orchestrator, distiller → mongo:27017     │
            └──────────────────────────────────┘
```

---

## Integration Test Fixture Model

### Test Session State

| Fixture | Scope | Description |
|---------|-------|-------------|
| `uim_client` | session | `httpx.AsyncClient` for user-input-manager |
| `tm_client` | session | `httpx.AsyncClient` for ticket-manager |
| `orch_client` | session | `httpx.AsyncClient` for orchestrator |
| `distiller_client` | session | `httpx.AsyncClient` for context-distiller |
| `uim_auth_headers` | session | Bearer token from UIM login (reused across tests) |
| `tm_auth_headers` | session | Bearer token from TM login (reused across tests) |
| `clean_db` | function | Truncates test-relevant tables before each test function |

### Scenario A — Test Data Flow

```
Step 1: POST /api/v1/auth/login (UIM) → access_token
Step 2: POST /api/v1/sessions (UIM) → session_id
Step 3: POST /api/v1/sessions/{id}/feedback {is_approved: false} → session (LLM mock called)
Step 4: POST /api/v1/sessions/{id}/feedback {is_approved: true} → session
Step 5: POST /api/v1/sessions/{id}/approve {ticket_title, project_description} → ticket_id
Step 6: GET  /api/v1/projects/{project_id}/tickets (TM) → ticket
Assert: ticket.tags contains "needs-estimation"
Assert: ticket.description starts with "[needs-estimation]"
```

### Scenario C — Test Data Flow

```
Step 1: POST /api/v1/auth/login (TM) → access_token
Step 2: PATCH /api/v1/tickets/{id}/fsm {status: "done"} (TM) → ticket
Step 3: POST /api/v1/orchestrator/jobs/trigger (UIM proxy) → job_id
Step 4: POLL GET /api/v1/orchestrator/jobs/{id} until status="done" (timeout: 30s)
Step 5: GET  /api/v1/orchestrator/memory/{project_id} → memory_content
Assert: memory_content is non-null
Assert: parsed YAML has required top-level keys
```
