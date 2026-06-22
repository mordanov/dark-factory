# Ticket Management System

A web application for tracking software delivery lifecycle progress across projects. Teams create and manage tickets, assign them to one or more users, and track per-assignee progress through a defined status workflow. The system supports agent-driven SDLC automation: a nine-agent team can bootstrap user accounts, create projects and tickets, transition statuses, and report resource usage — all through the API, without UI interaction. It also provides three-language UI localization, six selectable color themes, admin user lifecycle management, and URL-persisted board/list navigation. Every ticket action is recorded as an immutable timestamped event, forming a complete auditable history.

## Features

### Ticket Resource Tracking
- **Time and token counters** — every ticket carries `time_spent` (cumulative seconds) and `tokens_consumed` (cumulative units), both defaulting to 0
- **Increment-only API** — `POST /api/v1/tickets/{id}/resources` accepts non-negative deltas; arbitrary set or decrement operations are rejected
- **Immutable journal entries** — every increment emits a `ticket.resources_incremented` event recording the delta, resulting total, acting agent's identity, and UTC timestamp
- **Concurrent-safe** — the increment endpoint acquires a row-level lock (`SELECT FOR UPDATE`) to prevent lost updates when multiple agents write simultaneously
- **Unrestricted by assignment** — any authenticated user (including project administrator) may increment resource counters on any ticket

### Agent SDLC Automation
- **Agent user bootstrapping** — the `project-administrator` agent skill reads its own credential file, authenticates as platform admin, and ensures all eight other agent accounts exist before any SDLC run begins
- **Credential file management** — the project administrator writes `{role}/credentials.json` for each agent; missing accounts are created, invalid passwords are reset via `PATCH /api/v1/admin/users/{id}`
- **Bootstrap synchronization** — the project administrator broadcasts a `bootstrap-complete` signal via brainstorm-mcp after all credential files are written; other agent skills wait for this signal before reading credentials
- **Credential security** — all `*/credentials.json` files are gitignored and never committed; a `credentials.json.example` is provided as a format reference
- **Nine-agent team** — `project-administrator`, `product-manager`, `software-architect`, `security-architect`, `backend`, `frontend`, `devops`, `code-reviewer`, `autotester` — each has a dedicated working directory and credential file

### Transition Authorization (RBAC)
- **Assignee-only transitions** — only users currently listed as assignees on a ticket may initiate a status transition; all other users (including project administrator) receive HTTP 403
- **Progress gate remains** — every assignee must still submit a progress update before a transition is permitted (existing behavior, unchanged)
- **Administrator exception** — the project administrator may transition a ticket only if explicitly added as an assignee; having the `administrator` role does not bypass this check

### UI Personalization
- **Three-language interface** — full UI localization in English (`en`), Russian (`ru`), and Spanish (`es`)
- **Language switcher on every page** — language changes apply immediately without full page reload
- **Persistent language preference** — selected language is stored in `localStorage` (`lang` key), defaulting to English for first-time users and falling back to English for missing strings
- **Six accessible themes** — `light`, `dark`, `solarized`, `oceanic`, `high-contrast`, and `warm`
- **Persistent theme preference** — selected theme is stored in `localStorage` (`theme` key) and applied at app startup via `data-theme`

### Admin User Management
- **Admin-only user management page** — `/admin/users` is accessible to `administrator` users only
- **User lifecycle controls** — administrators can create users, edit user email/role, block users, unblock users, and reset passwords
- **Password reset** — `PATCH /api/v1/admin/users/{id}` accepts an optional `password` field; used by the project administrator skill during agent credential recovery
- **No user deletion** — accounts are retained; blocking is the deactivation mechanism
- **Self-protection rule** — administrators cannot block their own account (service-layer enforced)
- **Blocked login enforcement** — blocked users receive HTTP 403 on next login attempt with: `"Your account has been blocked. Contact an administrator."`

### Persistent URL Navigation
- Project board/list view is URL-backed via `?view=list|board`
- Refreshing or sharing project URLs preserves the current selected view
- Ticket detail pages remain directly addressable and refresh-safe via `/tickets/{ticketId}`

### Ticket Lifecycle
- **Primary tickets** — created within a project namespace with a title, description, and initial `OPEN` status
- **Follow-up tickets** — any authenticated user can create a follow-up linked to an existing ticket, inheriting its project namespace
- **Edit and delete** — ticket creators can edit title/description; deletion is blocked when active follow-up tickets exist (soft-delete: data retained for audit)

### Multi-Assignee Collaboration
- A ticket can be assigned to one or more users simultaneously
- Each assignee independently submits their own progress update (one updateable record per assignee)
- Status transitions are gated: **every assigned user must submit a progress update** before a transition is permitted
- The API identifies which assignees have not yet submitted when a transition is blocked

### Status Workflow
Hard-coded lifecycle enforced by `WorkflowService`:

```
OPEN → IN_PROGRESS → IN_REVIEW → DONE → CLOSED
                         ↓
                    IN_PROGRESS   (back from IN_REVIEW)
                         ↑
                      DONE        (back from DONE to IN_PROGRESS)
```

`CLOSED` is terminal — no further transitions are permitted. Only users assigned to a ticket may initiate a transition.

### Auditable Event History
Every domain action emits an immutable row to `ticket_events`:

| Event | Trigger |
|---|---|
| `ticket.created` | Ticket creation |
| `ticket.updated` | Title or description edit |
| `ticket.deleted` | Soft deletion |
| `ticket.assigned` | User assigned |
| `ticket.unassigned` | Assignment removed |
| `ticket.status_changed` | Successful transition |
| `ticket.progress_updated` | Progress record saved or updated |
| `ticket.transition_blocked` | Gate check failed |
| `ticket.resources_incremented` | Agent increments `time_spent` or `tokens_consumed` |

Each event carries the actor's identity, their role at the time of action, and UTC timestamp. The `ticket_events` table is append-only; a PostgreSQL trigger enforces this at the database level (migration `009`).

### Project Overview and Filtering
- List all tickets in a project with current status and assignees
- Filter by status or by assignee

### Authentication
- JWT-based auth (access token: 30-minute TTL, refresh token: revocable via the `refresh_tokens` table)
- Access tokens are stored in memory only (Zustand) — never in `localStorage` or `sessionStorage`
- Blocked users are denied on login (HTTP 403); existing active sessions continue until token expiry
- Two roles: `administrator` and `user`
- Agent skills authenticate via `POST /api/v1/auth/token` using credentials from their `{role}/credentials.json` file

---

## Architecture

```
┌─────────────────────┐      REST / JSON      ┌──────────────────────┐
│   React 18 SPA      │ ◄──────────────────► │   FastAPI backend     │
│   (Vite + TS)       │   /api/v1/*           │   (Python 3.11)       │
└─────────────────────┘                       └──────────┬───────────┘
                                                         │ asyncpg / SQLAlchemy 2.0
                                              ┌──────────▼───────────┐
                                              │   PostgreSQL 15       │
                                              └──────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  Agent Skills (Claude Code CLI + brainstorm-mcp)                    │
│  project-administrator · product-manager · software-architect       │
│  security-architect · backend · frontend · devops                   │
│  code-reviewer · autotester                                         │
│                                                                     │
│  Each skill: reads {role}/credentials.json → POST /auth/token       │
│              → uses JWT Bearer on all ticket platform API calls     │
└─────────────────────────────────────────────────────────────────────┘
```

**Key design decisions:**

- **Event-driven core** — `ticket_events` is the system of record. All mutations write an event row. The application layer never issues `UPDATE` or `DELETE` against this table.
- **Service layer isolation** — API handlers delegate all business logic to dedicated services (`TicketService`, `WorkflowService`, `TransitionService`, `EventService`, `ResourceService`, etc.). Handlers only do auth, validation, and response shaping.
- **Progress gate as a domain rule** — `WorkflowService` queries `progress_updates` before every transition. Missing rows block the transition and surface the specific assignees who have not submitted.
- **Row-level locking on transitions and resource increments** — `TransitionService` and `ResourceService` both issue `SELECT FOR UPDATE` to prevent race conditions under concurrent agent writes.
- **Assignee-only transition RBAC** — `TransitionService` checks that the acting user appears in the ticket's current assignment list before permitting any status change. Administrator role does not bypass this check.
- **Increment-only resource fields** — `time_spent` and `tokens_consumed` are modified only via `ResourceService.increment_resources`. Arbitrary set operations are not exposed through the API.
- **Soft delete** — `tickets.deleted_at` is set rather than hard-deleting rows. All queries filter `WHERE deleted_at IS NULL`. The event history is preserved.
- **UUID primary keys** — all tables use UUID v4 PKs. Sequential IDs are never exposed.
- **Versioned API** — all routes live under `/api/v1/`. Breaking changes require a new version prefix.
- **Append-only enforcement at the DB layer** — migration `009` installs a PostgreSQL trigger that raises an exception if any code attempts `UPDATE` or `DELETE` on `ticket_events`.
- **Admin controls are backend-enforced** — `/api/v1/admin/*` authorization is enforced server-side and not delegated to frontend routing alone.
- **UI preferences are client-scoped** — language and theme settings are persisted per-browser via `localStorage` and are intentionally not synced server-side.
- **Credential files are gitignored** — `*/credentials.json` files are excluded from version control. The `project-administrator` agent writes these files at runtime; they are never committed.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.11 |
| Web framework | FastAPI 0.136 |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Auth | python-jose (JWT) + bcrypt |
| Logging | structlog (JSON) |
| Database | PostgreSQL 15 |
| Frontend framework | React 18 + TypeScript 5 |
| Build tool | Vite |
| Routing | React Router v6 |
| Data fetching | TanStack Query v5 |
| State | Zustand |
| HTTP client | Axios |
| Backend tests | pytest + pytest-asyncio + httpx |
| Frontend tests | Vitest + React Testing Library |
| Agent coordination | Claude Code CLI + brainstorm-mcp |

---

## Prerequisites

| Tool | Minimum Version |
|---|---|
| Python | 3.11 |
| Node.js | 20 LTS |
| PostgreSQL | 15 |
| Docker | 24 (optional — for compose setup) |

---

## Running Locally

### 1. Backend

```bash
cd backend

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e ".[dev]"

cp .env.example .env
```

Edit `.env` — minimum required values:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ticket_manager
SECRET_KEY=<random-256-bit-hex>
REFRESH_TOKEN_SECRET=<random-256-bit-hex>
ENVIRONMENT=development
LOG_LEVEL=INFO
FRONTEND_URL=http://localhost:5173
```

Generate secrets:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> `SECRET_KEY` and `REFRESH_TOKEN_SECRET` must be at least 32 characters. The app refuses to start if either is shorter — this is intentional.

#### Database

```bash
# Option A: local Postgres
createdb ticket_manager

# Option B: Docker
docker run -d --name tms-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ticket_manager \
  -p 5432:5432 postgres:15
```

#### Migrations

```bash
alembic upgrade head
# Applies all migrations through current head (014_add_ticket_resource_fields)
```

#### Seed data (optional)

```bash
python scripts/seed_dev.py
# Creates: admin@example.com / admin123 (administrator role)
#          user@example.com  / user123  (user role)
# Creates: 1 project, 3 tickets in various statuses
```

#### Start API

```bash
uvicorn src.main:app --reload --port 8000
```

- `GET http://localhost:8000/health` → `{"status": "ok"}`
- `GET http://localhost:8000/ready` → `{"status": "ready"}`
- `GET http://localhost:8000/docs` → Interactive OpenAPI UI

---

### 2. Frontend

```bash
cd frontend

npm install

cp .env.local.example .env.local
# Set: VITE_API_BASE_URL=http://localhost:8000
```

```bash
npm run dev
# Visit http://localhost:5173
```

---

### 3. Full Stack via Docker Compose

```bash
# From repo root
docker compose up --build
```

Starts three services:
- `postgres` on port 5432
- `backend` on port 8000 (runs `alembic upgrade head` then `uvicorn`)
- `frontend` on port 5173 (nginx serving the built SPA)

---

### 4. Agent SDLC Run

```bash
# Place admin credentials for the project-administrator agent:
cp project-administrator/credentials.json.example project-administrator/credentials.json
# Edit credentials.json with the actual admin account email and password

# Launch the full nine-agent team:
bash run-agents.sh --project agent-api-sdlc
```

The agent run proceeds in this order:
1. `project-administrator` starts first, bootstraps all agent user accounts, and broadcasts a `bootstrap-complete` signal
2. `product-manager` (coordinator) waits for the signal, then creates a project and one ticket per task on the platform
3. Specialist agents claim their tickets, implement work, submit progress updates, transition tickets to DONE, and report `time_spent` and `tokens_consumed`
4. `project-administrator` reconciles metrics and generates the final HTML report

> **Credential files** — `project-administrator` writes `{role}/credentials.json` for each agent. These files are gitignored. Set `chmod 600` on each file in shared or production environments (see `devops/runbook.md` Section 11).

---

## Environment Variables

### Backend (`.env`)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | asyncpg connection string |
| `SECRET_KEY` | Yes | JWT signing key — min 32 chars |
| `REFRESH_TOKEN_SECRET` | Yes | Refresh token signing key — min 32 chars |
| `ENVIRONMENT` | Yes | `development` or `production` |
| `LOG_LEVEL` | No | Default: `INFO` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default: `30` |
| `FRONTEND_URL` | Yes | Used for CORS — must match browser origin exactly |

### Frontend (`.env.local`)

| Variable | Required | Description |
|---|---|---|
| `VITE_API_BASE_URL` | Yes | Backend base URL, e.g. `http://localhost:8000` |

---

## API Overview

All endpoints are under `/api/v1/`.

- Agent-oriented API guide: `docs/api-endpoints-agent-playbook.md`
- Core ticketing contract: `specs/001-ticket-management-system/contracts/openapi.yaml`
- Admin user management contract: `specs/002-ui-personalization-admin/contracts/openapi-admin.yaml`
- Resource tracking contract: `specs/003-agent-api-sdlc/contracts/resource-increment.md`
- Transition RBAC contract: `specs/003-agent-api-sdlc/contracts/transition-rbac.md`
- Runtime interactive docs: `GET /docs`

| Method | Path | Description |
|---|---|---|
| POST | `/auth/token` | Obtain access + refresh tokens (agent skills use this) |
| POST | `/auth/login` | Obtain access + refresh tokens (browser login form) |
| POST | `/auth/refresh` | Exchange refresh token for new access token |
| POST | `/auth/logout` | Revoke refresh token |
| GET | `/projects` | List projects |
| POST | `/projects` | Create a project |
| GET | `/projects/{id}/tickets` | List tickets (filter by status, assignee) |
| POST | `/projects/{id}/tickets` | Create a primary ticket |
| GET | `/tickets/{id}` | Get ticket detail (includes `time_spent`, `tokens_consumed`) |
| PATCH | `/tickets/{id}` | Edit ticket title/description |
| DELETE | `/tickets/{id}` | Soft-delete ticket |
| POST | `/tickets/{id}/assignments` | Assign a user |
| DELETE | `/tickets/{id}/assignments/{user_id}` | Remove an assignment |
| PUT | `/tickets/{id}/progress` | Submit or update your progress update |
| GET | `/tickets/{id}/progress` | List all assignees' progress updates |
| POST | `/tickets/{id}/transitions` | Attempt a status transition (assignees only) |
| POST | `/tickets/{id}/resources` | Increment `time_spent` and/or `tokens_consumed` |
| GET | `/tickets/{id}/events` | Paginated activity history |
| GET | `/admin/users` | List all users (admin only) |
| POST | `/admin/users` | Create a user (admin only) |
| PATCH | `/admin/users/{id}` | Edit a user — email, role, or password (admin only) |
| POST | `/admin/users/{id}/block` | Block a user (admin only; self-block forbidden) |
| POST | `/admin/users/{id}/unblock` | Unblock a user (admin only) |

### Resource increment request/response

```http
POST /api/v1/tickets/{ticket_id}/resources
Authorization: Bearer <access_token>
Content-Type: application/json

{"time_spent_delta": 120, "tokens_consumed_delta": 500}
```

```json
{"ticket_id": "...", "time_spent": 240, "tokens_consumed": 1500, "event_id": "..."}
```

Validation: both deltas must be `>= 0` (negative → 422); at least one must be `> 0` (both zero → 400).

---

## Running Tests

### Backend

```bash
cd backend

pytest                        # all tests
pytest tests/unit/            # pure unit tests (no DB)
pytest tests/integration/     # requires live PostgreSQL
pytest tests/contract/        # validates responses against contracts

# Specific contract suites
pytest tests/contract/test_resources.py         # resource increment endpoint (12 scenarios)
pytest tests/contract/test_admin.py             # admin API including password reset
pytest tests/contract/test_transitions.py       # transition RBAC (non-assignee → 403)
pytest tests/integration/test_auth_blocked.py   # blocked-user login flow
```

### Frontend

```bash
cd frontend

npm test                      # Vitest single-run
npm run test:watch            # Vitest watch mode
npm run test:coverage         # with coverage report
npm run typecheck             # TypeScript type check only
npm run test -- LanguageSwitcher
npm run test -- ThemeSwitcher
npm run test -- AdminUsersPage
npm run test -- ProjectPage.url
```

---

## Assumptions and Scope Decisions

1. **Ticket statuses are hard-coded.** `OPEN → IN_PROGRESS → IN_REVIEW → DONE → CLOSED`. Workflow configurability is a future concern.

2. **No project-level access control.** All authenticated users can read and act on all projects and tickets. This is an explicit scope decision for a small internal team tool. If the system ever becomes multi-tenant, per-project membership controls become a blocker.

3. **"Product owner" is not a system role.** The system has two roles: `administrator` and `user`. Any authenticated user may create primary or follow-up tickets.

4. **Progress update is one updateable record per (ticket, assignee).** Each new submission replaces the previous content, but every submission is recorded as a `ticket.progress_updated` event, so the full history is traceable.

5. **Assignee removal does not delete progress records.** Removed assignees' progress records remain in the history. Assignment removal itself is recorded as a `ticket.unassigned` event.

6. **Ticket deletion is soft.** `deleted_at` is set; the ticket and its events are never removed from the database. This preserves the audit trail.

7. **No external message broker.** Events are written synchronously within the same database transaction as the triggering action. This is appropriate for the expected scale (10–200 concurrent users).

8. **JWT access tokens are not revocable.** After logout, the refresh token is revoked, but an intercepted access token remains valid for up to 30 minutes (standard JWT tradeoff). The short TTL and memory-only client storage mitigate this.

9. **No rate limiting in the application layer.** Rate limiting on `/auth/login` is expected to be handled by the reverse proxy in production.

10. **User deactivation is block/unblock only.** Admins cannot delete users; account data is retained for auditability.

11. **Block enforcement timing is next login.** Blocking does not terminate an already-issued access token; active sessions expire naturally.

12. **Theme catalog is fixed at six schemes.** `light`, `dark`, `solarized`, `oceanic`, `high-contrast`, and `warm` are the supported set for this feature scope.

13. **Resource counters are increment-only and monotonic.** `time_spent` and `tokens_consumed` can only increase. There is no API to decrement or reset these fields. This preserves the integrity of the audit trail.

14. **Agent credential files are runtime-generated and gitignored.** The project administrator creates `{role}/credentials.json` at the start of each SDLC run. These files are never committed. The `project-administrator/credentials.json` (the admin's own credentials) is provided by a human operator before the first run.

15. **Agent accounts use the `user` role.** All agent skill accounts are created as platform `user` accounts. The project administrator authenticates as an `administrator` account (provided by the human operator). No new role is needed.

---

## Security Notes

- Passwords are hashed with bcrypt. Plaintext passwords are never stored or logged.
- JWT access tokens are stored in memory only (Zustand) — not in `localStorage` or `sessionStorage`.
- Refresh tokens are stored server-side as SHA-256 hashes, supporting revocation.
- `ticket_events` is enforced append-only by both the application layer and a PostgreSQL trigger (migration `009`). No `UPDATE` or `DELETE` is ever issued against this table.
- CORS is restricted to `FRONTEND_URL` only. `allow_origins=["*"]` is not used.
- Role-based and assignment-based access control is enforced in FastAPI dependency functions before any handler executes.
- **Transition RBAC** — only assignees may transition a ticket; the `administrator` role does not bypass this. `TransitionService` checks the assignment list before permitting any status change.
- Admin actions are restricted to `administrator` role server-side for all `/api/v1/admin/*` endpoints.
- Admin user-management actions are auditable via structured logs including actor and target IDs.
- Self-targeted admin safety checks prevent own-account block actions.
- **Agent credential files** — all `*/credentials.json` files are listed in `.gitignore`. They must never be committed to version control. In shared or production environments, set file permissions to `600` (see `devops/runbook.md` Section 11).
- **Password reset audit** — `PATCH /api/v1/admin/users/{id}` with a `password` field emits a structured `admin_user_password_reset` log event with actor and target IDs. The new password value is never logged.
- Structured JSON logs (structlog) exclude sensitive fields. Stack traces are suppressed in `production` mode.

See `devops/security-review.md` and `devops/security-review-003.md` for the full threat model, finding catalog, and accepted residual risks.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ValidationError: secret_key` at startup | `SECRET_KEY` shorter than 32 chars | Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `connection refused` on port 5432 | Postgres not running | Start Postgres or Docker container |
| `alembic: command not found` | venv not activated | `source .venv/bin/activate` |
| `401 Unauthorized` on all endpoints | Access token expired (30-min TTL) | Re-login to get a fresh token |
| `403 Your account has been blocked` at login | User account has `blocked_at` set | Ask an administrator to unblock the account |
| Transition returns 422 with `missing_updates` | Not all assignees have submitted progress | Each assignee must `PUT /api/v1/tickets/{id}/progress` before transitioning |
| Transition returns 403 | Caller is not in the ticket's assignee list | Add the user as an assignee, or use an account that is already assigned |
| Resource increment returns 400 | Both `time_spent_delta` and `tokens_consumed_delta` are 0 | At least one delta must be greater than 0 |
| Resource increment returns 422 | A delta value is negative | Deltas must be `>= 0`; resource fields are increment-only |
| Agent run halts: `Bootstrap signal not received` | `project-administrator` did not complete bootstrapping within 120s | Check `project-administrator` logs; ensure its `credentials.json` exists and the platform is reachable |
| Agent run halts: `credentials.json not found` | Credential file missing for the agent role | Run the project-administrator bootstrap step, or place the file manually |
| CORS errors in browser | `FRONTEND_URL` mismatch | Ensure `FRONTEND_URL` in backend `.env` matches the browser origin exactly |
| Alembic is behind latest head revision | Not all migrations are applied (current head: `014_add_ticket_resource_fields`) | Run `alembic upgrade head` |

---

## Project Layout

```
ticket-manager/
├── agents/                         # agent skill definition files
│   ├── product-manager.md
│   ├── software-architect.md
│   ├── security-architect.md
│   ├── backend-developer-python.md
│   ├── frontend-developer-react.md
│   ├── devops.md
│   ├── code-reviewer.md
│   ├── autotester.md
│   └── project-administrator.md
├── product-manager/                # agent working directory
│   └── credentials.json            # gitignored — written by project-administrator
├── software-architect/             # agent working directory
│   └── credentials.json            # gitignored
├── security-architect/             # agent working directory
│   └── credentials.json            # gitignored
├── backend/
│   ├── alembic/versions/           # migrations (current head: 014_add_ticket_resource_fields)
│   ├── src/
│   │   ├── main.py
│   │   ├── core/                   # config, database, security, logging
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   ├── services/               # business logic (ticket, workflow, transition, event, resource…)
│   │   └── api/v1/                 # FastAPI route handlers
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── contract/
│   ├── scripts/seed_dev.py
│   └── credentials.json            # gitignored — agent working directory
├── frontend/
│   ├── src/
│   │   ├── api/                    # typed API client functions
│   │   ├── locales/                # i18n dictionaries (en/ru/es)
│   │   ├── components/             # React components
│   │   │   ├── admin/              # admin user-management UI
│   │   │   └── common/             # language/theme switchers
│   │   ├── hooks/                  # custom hooks (including useTheme)
│   │   ├── pages/                  # route-level page components
│   │   └── store/auth.ts           # Zustand auth state (memory-only tokens)
│   ├── tests/
│   └── credentials.json            # gitignored — agent working directory
├── devops/
│   ├── runbook.md                  # operational runbook (incl. credential file permissions)
│   ├── security-review.md          # threat model — feature 001
│   ├── security-review-admin.md    # threat model — feature 002 (admin management)
│   └── security-review-003.md      # threat model — feature 003 (agent SDLC)
├── project-administrator/
│   ├── agent_metrics.py            # SQLite metrics CLI tool
│   ├── agent_metrics.sqlite3       # local metrics database (gitignored)
│   ├── credentials.json            # gitignored — provided by human operator
│   ├── credentials.json.example    # format reference (committed)
│   └── README.md
├── specs/001-ticket-management-system/
│   ├── spec.md
│   ├── plan.md
│   ├── data-model.md
│   ├── quickstart.md
│   └── contracts/openapi.yaml
├── specs/002-ui-personalization-admin/
│   ├── spec.md
│   ├── plan.md
│   ├── quickstart.md
│   └── contracts/openapi-admin.yaml
├── specs/003-agent-api-sdlc/
│   ├── spec.md                     # feature specification
│   ├── plan.md                     # implementation plan and constitution check
│   ├── data-model.md               # schema changes
│   ├── research.md                 # phase 0 decisions
│   ├── quickstart.md               # end-to-end test walkthrough
│   ├── tasks.md                    # 25 implementation tasks across 6 phases
│   └── contracts/
│       ├── resource-increment.md   # POST /tickets/{id}/resources contract
│       ├── admin-password-reset.md # PATCH /admin/users/{id} password field
│       └── transition-rbac.md      # assignee-only transition enforcement
├── run-agents.sh                   # launches the nine-agent SDLC team
└── docker-compose.yml
```
