# Developer Quickstart: Ticket Management System

**Branch**: `001-ticket-management-system`

This guide gets a local development environment running from scratch. It covers
backend, frontend, database, and the basic end-to-end flow to verify your setup.

---

## Prerequisites

| Tool | Minimum Version | Notes |
|------|----------------|-------|
| Python | 3.11 | Use `pyenv` or system package manager |
| Node.js | 20 LTS | Use `nvm` or system package manager |
| PostgreSQL | 15 | Local install or Docker |
| Docker | 24 (optional) | For Postgres-in-container setup or full stack via docker-compose |

---

## 1. Clone and Repository Layout

```bash
git clone <repo-url>
cd ticket-manager
```

```
ticket-manager/
├── backend/        # FastAPI Python service
├── frontend/       # React TypeScript SPA
├── devops/         # Runbooks and security reviews
└── specs/          # Specification artifacts (non-executable)
```

---

## 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate

# Install dependencies (uses pyproject.toml — no separate requirements files)
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
```

Edit `.env` — minimum required values:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ticket_manager
SECRET_KEY=<random-256-bit-hex>       # must be ≥32 chars — app will not start otherwise
REFRESH_TOKEN_SECRET=<random-256-bit-hex>  # must be ≥32 chars
ENVIRONMENT=development
LOG_LEVEL=INFO
FRONTEND_URL=http://localhost:5173    # used for CORS — must match your frontend URL
```

Generate secure secret values:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> **Note**: `SECRET_KEY` and `REFRESH_TOKEN_SECRET` are validated at startup.
> If either is shorter than 32 characters, the app will fail to start with a
> `ValidationError`. This is intentional.

### 2a. Database

**Option A — local PostgreSQL:**

```bash
createdb ticket_manager
```

**Option B — Docker:**

```bash
docker run -d --name tms-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ticket_manager \
  -p 5432:5432 postgres:15
```

### 2b. Run Migrations

```bash
alembic upgrade head
```

Expected output: **9 migration steps** (`001` through `009`), each confirming `Running upgrade`.

Migration summary:
- `001` — ENUM types (`user_role`, `ticket_status`)
- `002`–`008` — Core tables (users, projects, tickets, assignments, progress, events, refresh_tokens)
- `009` — PostgreSQL trigger enforcing append-only immutability on `ticket_events`

### 2c. Seed a Test User (optional)

```bash
python scripts/seed_dev.py
# Creates: admin@example.com / admin123 (administrator)
#          user@example.com  / user123  (user)
# Creates: 1 project + 3 tickets in various statuses
```

### 2d. Start the API

```bash
uvicorn src.main:app --reload --port 8000
```

Verify:
- `GET http://localhost:8000/health` → `{"status": "ok"}`
- `GET http://localhost:8000/ready` → `{"status": "ready"}`
- `GET http://localhost:8000/docs` → Interactive OpenAPI UI

---

## 3. Frontend Setup

```bash
cd ../frontend

npm install

cp .env.local.example .env.local
```

Edit `.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

### 3a. Start Dev Server

```bash
npm run dev
```

Visit `http://localhost:5173` — login with seeded credentials.

---

## 4. Full Stack via Docker Compose (alternative)

```bash
# From repo root
docker compose up --build
```

Services started:
- `postgres` on port 5432
- `backend` on port 8000 (runs `alembic upgrade head` then `uvicorn`)
- `frontend` on port 80 (nginx serving the built SPA)

---

## 5. End-to-End Smoke Test

Use the OpenAPI UI (`/docs`) or `curl` to verify the core flow:

```bash
# 1. Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"user123"}' \
  | jq -r .access_token)

# 2. Create a ticket (replace PROJECT_ID with a real UUID from seed data)
curl -s -X POST http://localhost:8000/api/v1/projects/$PROJECT_ID/tickets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"First ticket","description":"Smoke test"}'

# 3. Check activity history
curl -s http://localhost:8000/api/v1/tickets/$TICKET_ID/events \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Expected: the `ticket.created` event appears in the history with your user ID.

---

## 6. Running Tests

### Backend

```bash
cd backend
pytest                              # all tests
pytest tests/unit/                  # unit tests only
pytest tests/integration/           # requires live PostgreSQL
pytest tests/contract/              # contract tests against openapi.yaml
```

### Frontend

```bash
cd frontend
npm test                            # Vitest single-run
npm run test:watch                  # Vitest watch mode
npm run typecheck                   # TypeScript type check
```

---

## 7. Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ValidationError: secret_key` at startup | SECRET_KEY shorter than 32 chars | Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `connection refused` on port 5432 | Postgres not running | Start Postgres or Docker container |
| `alembic: command not found` | venv not activated | `source .venv/bin/activate` |
| `401 Unauthorized` on all endpoints | Token expired (30-min TTL) | Re-login to get a fresh token |
| Transition returns 422 with `missing_updates` | Not all assignees have submitted progress | Each assignee must `PUT /api/v1/tickets/{id}/progress` before transitioning |
| CORS errors in browser | FRONTEND_URL mismatch | Ensure `FRONTEND_URL` in backend `.env` matches the browser origin exactly |
| Alembic reports 8 steps instead of 9 | Old migration count cached | Run `alembic upgrade head` — migration 009 adds the `ticket_events` immutability trigger |

---

## 8. Key Files for Onboarding

| File | Purpose |
|------|---------|
| `backend/src/services/transition_service.py` | Workflow transition with progress gate + row-level locking |
| `backend/src/services/event_service.py` | Event emission for all domain actions |
| `backend/src/api/v1/transitions.py` | Status transition endpoint |
| `backend/alembic/versions/` | All 9 schema migrations |
| `backend/alembic/versions/009_ticket_events_immutable_trigger.py` | DB-level append-only enforcement |
| `specs/001-ticket-management-system/contracts/openapi.yaml` | Full API contract |
| `specs/001-ticket-management-system/data-model.md` | Entity definitions and relationships |
| `devops/runbook.md` | Operational runbook: health probes, JWT lifecycle, incident diagnosis |
| `devops/security-review.md` | Security review, residual risks, and remediation targets |

---

## 9. Implementation Deviations from Original Plan

These items differ from what was specified in `plan.md` and are recorded here per T083:

| Area | Plan Said | Actual |
|------|-----------|--------|
| Backend dependencies | `requirements.txt` + `requirements-dev.txt` | `pyproject.toml` with `pip install -e ".[dev]"` |
| Migration count | 8 steps (001–008) | 9 steps — migration 009 adds the `ticket_events` immutability trigger (F-EVT-01 security fix) |
| Environment vars | No `FRONTEND_URL` | `FRONTEND_URL` required for CORS; defaults to `http://localhost:5173` |
| Secret validation | Not specified | `SECRET_KEY` and `REFRESH_TOKEN_SECRET` validated ≥32 chars at startup; app refuses to start otherwise |
| CORS | Not specified | `CORSMiddleware` in `main.py` restricts origins to `FRONTEND_URL` only |
| Transition locking | Not specified | `transition_service.py` uses `SELECT FOR UPDATE` on ticket + assignments rows to prevent race conditions |
| Docker | Optional | `backend/Dockerfile`, `frontend/Dockerfile` (multi-stage nginx), `docker-compose.yml` created |
| Frontend auth store | `localStorage` not mentioned | `store/auth.ts` explicitly stores tokens in memory only (Zustand) — never `localStorage`/`sessionStorage` |
