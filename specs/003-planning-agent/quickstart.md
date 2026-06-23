# Quickstart: Planning Agent for Prompt Studio

**Feature**: `003-planning-agent`
**Date**: 2026-06-23

## Prerequisites

- Docker and Docker Compose installed
- `infra/.env` filled (copy from `infra/.env.example`; set `OPENAI_API_KEY`,
  `POSTGRES_PASSWORD`, `TICKET_MANAGER_SERVICE_EMAIL`, `TICKET_MANAGER_SERVICE_PASSWORD`,
  `CONTEXT_DISTILLER_BASE_URL=http://context-distiller:8004`)
- Monorepo root: `dark-factory/`

## Run as Part of the Monorepo

```bash
# Start everything (first time will build images)
docker compose -f infra/docker-compose.yml up --build

# Apply user-input-manager DB migrations (if not auto-applied in entrypoint)
docker compose -f infra/docker-compose.yml exec user-input-manager \
  alembic upgrade head

# Apply context-distiller DB migrations
docker compose -f infra/docker-compose.yml exec context-distiller \
  alembic upgrade head
```

## Run user-input-manager in Isolation

```bash
cd services/user-input-manager

# Start with standalone compose (includes local postgres)
docker compose up --build

# Apply migrations
docker compose exec backend alembic upgrade head
```

## New Environment Variables

Add to `infra/.env` (and `services/user-input-manager/backend/.env` for isolated dev):

```env
# Planning Agent — model for agent config generation (cheaper model is fine)
PLANNING_MODEL=gpt-4o-mini

# ContextDistiller integration
CONTEXT_DISTILLER_BASE_URL=http://context-distiller:8004
CONTEXT_DISTILLER_TIMEOUT_SECONDS=10
```

## Run Backend Tests

```bash
cd services/user-input-manager/backend
pytest --cov=src --cov-report=term-missing -q
```

Coverage target: ≥ 80% lines and functions.

Unit tests (no DB required):
```bash
pytest tests/unit/ -q
```

Integration tests (require local postgres from docker compose):
```bash
pytest tests/integration/ -q
```

## Run Frontend Tests

```bash
cd services/user-input-manager/frontend
npm run test        # run Vitest in watch mode
npm run test -- --run   # run once (CI mode)
npm run coverage    # coverage report
```

## Manual End-to-End Walkthrough

1. **Login**: `POST /api/auth/login` → get `access_token`
2. **Create session**: `POST /api/v1/sessions` with `initial_prompt` and `session_type`
3. **Submit feedback** (optional): `POST /api/v1/sessions/{id}/feedback`
4. **Approve prompt** — this is now done implicitly. When the last iteration has
   `is_approved = true`, call `PATCH /api/v1/sessions/{id}` to set `status = approved`
   (or use the frontend "Approve" button which now triggers plan generation directly).

   > Note: `POST /sessions/{id}/approve` endpoint is removed. The frontend
   > "Approve prompt" step now transitions the session to `approved` status and
   > immediately shows the "Generate Plan" button.

5. **Trigger plan generation**: `POST /api/v1/sessions/{id}/plan` → 202
6. **Poll until ready**: `GET /api/v1/sessions/{id}/plan` until `status = "ready"`
7. **Edit plan** (optional): `PUT /api/v1/sessions/{id}/plan` with updated `plan_content`
8. **Confirm plan**: `POST /api/v1/sessions/{id}/plan/confirm` → 202
9. **Poll creation status**: `GET /api/v1/sessions/{id}/plan/status`
   until `status = "tickets_created"` or `"error"`
10. **On error** (partial failure): retry `POST /api/v1/sessions/{id}/plan/confirm`
    — already-created tickets are skipped automatically.

## Configure PLANNING_MODEL

```bash
# Use default (gpt-4o-mini for agent config, gpt-4o-mini for plan generation)
PLANNING_MODEL=gpt-4o-mini

# Use a different model for both LLM calls
PLANNING_MODEL=gpt-4o
OPENAI_MODEL=gpt-4o  # (already controls the main LLM; planning LLM uses PLANNING_MODEL)
```

`PLANNING_MODEL` controls the agent config generation call only.
Plan generation uses the same model as `OPENAI_MODEL`.

## Context-Distiller agent-config Endpoints

```bash
# Store agent config (called automatically by planning service; can also be called directly)
curl -X POST http://localhost:8004/api/v1/memory/{project_id}/agent-config \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"project_id":"proj1","tech_stack":["Python","React"],"agent_overrides":[]}'

# Retrieve agent config
curl http://localhost:8004/api/v1/memory/{project_id}/agent-config \
  -H "Authorization: Bearer <token>"
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `POST .../plan` returns 409 | Session not in `approved` status | Check session status via `GET /sessions/{id}` |
| Plan generation hangs > 60s | LLM timeout | Check `OPENAI_API_KEY`, `OPENAI_BASE_URL`; increase `openai_timeout_seconds` |
| `PUT .../plan` returns 409 | Plan already confirmed | Cannot edit a confirmed plan |
| Ticket creation stalls at partial count | TM API intermittent failure | Retry via `POST .../plan/confirm` |
| Agent config always null | ContextDistiller unreachable | Check `CONTEXT_DISTILLER_BASE_URL`; this is best-effort and does not block tickets |
