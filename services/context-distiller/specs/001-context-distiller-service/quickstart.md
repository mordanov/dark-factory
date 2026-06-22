# Quickstart: ContextDistiller Service

**Date**: 2026-06-20

---

## Prerequisites

- Docker + Docker Compose with existing Dark Factory stack running
  (`postgres`, `mongo`, `orchestrator`, `user-input-manager` / Prompt Studio)
- `.env` file at `context-distiller/` root (see `.env.example`)

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

```env
# PostgreSQL — same DB as Orchestrator
DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/df_orchestrator

# MongoDB — same instance as Orchestrator
MONGO_URL=mongodb://mongo:27017
MONGO_DB_NAME=dark_factory_docs

# JWT — must match Prompt Studio exactly
JWT_SECRET_KEY=your-shared-secret
JWT_ALGORITHM=HS256

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=120

# Ticket Manager
TICKET_MANAGER_BASE_URL=http://ticket-manager:8000
TICKET_MANAGER_SERVICE_EMAIL=distiller@dark-factory.internal
TICKET_MANAGER_SERVICE_PASSWORD=changeme

# Worker tuning
DISTILLER_MAX_MEMORY_TOKENS=2000
DISTILLER_MEMORY_HISTORY_KEEP=20
WORKER_MAX_CONCURRENT_JOBS=3
WORKER_POLL_INTERVAL_SECONDS=5
```

---

## Running Locally (Docker Compose)

Add the service to `docker-compose.override.yml` (or the main `docker-compose.yml`):

```yaml
context-distiller:
  build: ./context-distiller
  env_file: ./context-distiller/.env
  depends_on:
    - postgres
    - mongo
  ports:
    - "8002:8000"
  restart: unless-stopped
```

Then:
```bash
docker compose up --build context-distiller
```

Health check:
```bash
curl http://localhost:8002/api/health
# → {"status": "ok"}
```

---

## Running Tests

```bash
cd context-distiller
python -m pytest tests/ -v --cov=src --cov-report=term-missing
# Coverage must be ≥ 80% (enforced by .coveragerc)
```

---

## Triggering a Distillation Manually

Obtain a JWT from Prompt Studio:
```bash
TOKEN=$(curl -s -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@df.local","password":"changeme"}' \
  | jq -r .access_token)
```

Enqueue a distill job:
```bash
curl -X POST http://localhost:8002/distill \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ticket_id": "TICKET-001", "project_id": "my-project"}'
# → {"job_id": "..."}
```

Poll until done:
```bash
curl http://localhost:8002/status/<job_id> \
  -H "Authorization: Bearer $TOKEN"
# → {"job_id": "...", "status": "done", "error": null}
```

Retrieve memory:
```bash
curl http://localhost:8002/memory/my-project \
  -H "Authorization: Bearer $TOKEN"
# → {"project_id": "my-project", "content": "...", "version": 1, ...}
```

---

## Verification Checklist (Definition of Done)

- [ ] `docker build .` succeeds with no errors
- [ ] `docker compose up context-distiller` starts cleanly alongside existing services
- [ ] `GET /api/health` returns `{"status": "ok"}`
- [ ] `POST /distill` with a real ticket ID enqueues a job (202)
- [ ] `GET /status/{job_id}` reaches `done` within 30 seconds
- [ ] `GET /memory/{project_id}` returns valid YAML with all required fields
- [ ] Running the same distill job twice produces no errors and no duplicate `recent_changes`
- [ ] Test suite passes with ≥ 80% coverage: `pytest --cov=src`
