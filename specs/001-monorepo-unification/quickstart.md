# Quickstart: Dark Factory Monorepo

## Prerequisites

- Docker 24+ with Compose v2 (`docker compose` command available)
- Git
- A Unix-like shell (macOS or Linux)

## First-time setup

```bash
# 1. Clone the repo
git clone <repo-url> dark-factory && cd dark-factory

# 2. Create your .env from the template
cp infra/.env.example infra/.env

# 3. Edit infra/.env — fill in all required values (no defaults have passwords)
#    Required at minimum:
#      POSTGRES_USER, POSTGRES_PASSWORD
#      UIM_DB_USER, UIM_DB_PASSWORD, UIM_SECRET_KEY
#      TM_DB_USER, TM_DB_PASSWORD, TM_SECRET_KEY
#      ORCH_DB_USER, ORCH_DB_PASSWORD, ORCH_SECRET_KEY
#      DISTILLER_DB_USER, DISTILLER_DB_PASSWORD
#      UIM_HOST, TM_HOST  (e.g. localhost for local dev)
#      OPENAI_API_KEY

# 4. Start the full platform
docker compose -f infra/docker-compose.yml up --build

# 5. Verify all services are healthy
docker compose -f infra/docker-compose.yml ps
```

All services are ready when every container shows `healthy` in `docker compose ps`.

## Local development (port access)

Use the dev override to expose service ports directly:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml up --build
```

Services are then accessible at:

| Service | URL |
|---------|-----|
| user-input-manager API | http://localhost:8001 |
| ticket-manager API | http://localhost:8002 |
| orchestrator API | http://localhost:8003 |
| context-distiller API | http://localhost:8004 |
| agent-tools API | http://localhost:8005 |

## Running a single service in isolation

Each service has its own `docker-compose.yml` for standalone development:

```bash
docker compose -f services/user-input-manager/docker-compose.yml up --build
```

The service uses its own local postgres/mongo instances when running in isolation.

## Running integration tests

```bash
# Start test environment (adds LLM mock, overrides OPENAI_BASE_URL)
docker compose -f integration-tests/docker-compose.test.yml up --build -d

# Run integration test suite
cd integration-tests
pip install -r requirements.txt
pytest tests/ -v

# Tear down
docker compose -f integration-tests/docker-compose.test.yml down -v
```

## Pre-commit hooks

```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Run all hooks manually
pre-commit run --all-files
```

## Service map

| Service | Internal port | Database (PG) | Database (Mongo) | Has frontend |
|---------|--------------|---------------|-----------------|--------------|
| user-input-manager | 8001 | df_user_input | — | yes |
| ticket-manager | 8002 | df_ticket_manager | — | yes |
| orchestrator | 8003 | df_orchestrator | df_orchestrator_docs | no |
| context-distiller | 8004 | df_distiller | df_distiller_docs | no |
| agent-tools | 8005 | — | — | no |

Internal service URLs: `http://{service-name}:{port}` (Docker internal DNS).

## Troubleshooting

**Services fail to start: "password authentication failed"**
→ Check `infra/.env` has correct `*_DB_USER` and `*_DB_PASSWORD` values.
→ Destroy the postgres volume and restart: `docker compose down -v && docker compose up --build`

**`AUTH_MODE` startup error**
→ Ensure `*_AUTH_MODE` is either `local` or `keycloak` (or omitted to default to `local`).

**Frontend not loading through nginx**
→ Verify `UIM_HOST` / `TM_HOST` in `.env` match the hostname you're accessing in the browser.
→ For localhost development, set both to `localhost` and add host entries if needed.
