# AGENTS.md

## Read this codebase in this order
1. `README.md` for the current monorepo map and startup flow.
2. `specs/004-keycloak-iam-migration/plan.md` for the current auth architecture and cross-service constraints.
3. `infra/docker-compose.yml` + `infra/docker-compose.override.yml` for the real runtime topology, ports, healthchecks, and env wiring.

## Big picture
- Dark Factory is a six-service monorepo: `user-input-manager`, `ticket-manager`, `orchestrator`, `context-distiller`, `agent-tools`, `agent-dispatcher`.
- Runtime boundaries are HTTP over the internal Docker network, not shared Python packages. If you change a cross-service pattern, keep it copy-consistent per service rather than introducing a shared backend library.
- Only `orchestrator` and `context-distiller` use MongoDB; all other durable state is per-service PostgreSQL.
- `agent-dispatcher` is the automation hinge: it polls Orchestrator, runs agents in `claude_code` or `api` mode, and posts results back to Ticket Manager.

## Choose your lane

### If you are a backend implementation agent
- Start from the target service's `src/main.py`, `src/core/config.py`, `src/core/auth_adapter.py`, and the relevant router/service/client files.
- Follow the FastAPI app-factory + lifespan pattern used in `services/user-input-manager/backend/src/main.py`: shared `AppError` handling, CORS middleware, router registration, and startup JWKS prefetch.
- Keep runtime config inside `src/core/config.py` via `pydantic-settings` + cached `get_settings()`; avoid ad-hoc `os.environ` reads elsewhere.
- Treat Keycloak as the runtime auth source of truth. The active pattern is `KeycloakValidator` as in `services/user-input-manager/backend/src/core/auth_adapter.py`; tests may still exercise `AUTH_MODE=local`.
- Use internal Docker URLs like `http://ticket-manager:8000`, not host-mapped ports, in service clients and defaults.

### If you are a full-stack / productivity agent
- Backend + frontend changes often come in pairs: check the service frontend store/API client alongside backend schema/router changes.
- Frontend auth is in-memory `keycloak-js` + Zustand, e.g. `services/user-input-manager/frontend/src/store/auth.ts`; do not introduce `localStorage`/`sessionStorage` token persistence.
- Root `package.json` is a version ledger only, not a workspace. Install and run Node dependencies inside each service frontend.
- When auth, routing, or API behavior changes, also inspect nginx and compose wiring because browser-visible behavior depends on `infra/nginx/` plus Keycloak/oauth2-proxy.

### If you are a multi-agent orchestration contributor
- Read `development/run-agents.sh` first; it encodes the real brainstorm workflow, role startup order, terminal-launch behavior, and dry-run validation.
- Read the role prompts in `development/agents/*.md` before changing agent coordination semantics.
- `agent-dispatcher` behavior is defined by code and env together: see `services/agent-dispatcher/README.md`, `infra/.env.example`, and dispatcher service env in `infra/docker-compose.yml`.
- Brainstorm/result handling is product behavior, not incidental plumbing: agent output parsing, round limits, and downstream Ticket Manager reporting must stay compatible.

## Auth and docs reality
- Compose runs every backend with `AUTH_MODE=keycloak`; `AUTH_MODE=local` is reserved for tests in `integration-tests/docker-compose.test.yml`.
- `integration-tests/conftest.py` and the test compose still use seeded local users and HMAC-style flows intentionally.
- Some service READMEs still describe legacy `/api/v1/auth/login` local JWT flows. For auth work, trust current source, root docs, and `specs/004-keycloak-iam-migration/plan.md` over older per-service README text.

## Workflows that matter
```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml up --build
```
```bash
docker compose -f integration-tests/docker-compose.test.yml up --build -d
pytest integration-tests/ -v
docker compose -f integration-tests/docker-compose.test.yml down -v
```
```bash
pre-commit run --all-files
bash development/run-agents.sh --dry-run
```
- Keycloak first boot is slow; `infra/KEYCLOAK.md` says to allow up to ~5 minutes for realm import and healthchecks.
- Python style is monorepo-wide: `ruff` with line length 100 and `py312` from `pyproject.toml`; root pre-commit only targets `services/**/*.py`.

## Cross-service traces to follow before editing
- `user-input-manager` calls Ticket Manager and Context Distiller during prompt approval and planning.
- `orchestrator` drives ticket FSM transitions and uses Context Distiller memory; inspect its clients before changing ticket lifecycle behavior.
- `agent-dispatcher` depends on Orchestrator, Ticket Manager, and Context Distiller URLs/env vars from `infra/.env.example`; result parsing and brainstorm rounds are service behavior.
- For any cross-service feature, read the neighboring service API/router/schema files at `../` scope before editing only one side; service-level `CLAUDE.md` files explicitly call this out.


