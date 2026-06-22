<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/001-monorepo-unification/plan.md`
<!-- SPECKIT END -->

# Dark Factory Monorepo

## Service Map

| Service | Directory | Host Port (dev override) | Database | Internal URL |
|---------|-----------|--------------------------|----------|--------------|
| user-input-manager | `services/user-input-manager/backend` | 8001 | `df_user_input` (PostgreSQL) | `http://user-input-manager:8000` |
| ticket-manager | `services/ticket-manager/backend` | 8002 | `df_ticket_manager` (PostgreSQL) | `http://ticket-manager:8000` |
| orchestrator | `services/orchestrator` | 8003 | `df_orchestrator` (PostgreSQL + MongoDB `df_orchestrator_docs`) | `http://orchestrator:8000` |
| context-distiller | `services/context-distiller` | 8004 | `df_distiller` (PostgreSQL + MongoDB `df_distiller_docs`) | `http://context-distiller:8000` |
| agent-tools | `services/agent-tools` | 8005 | none | `http://agent-tools:8000` |

## Infrastructure

| Component | Location |
|-----------|----------|
| Unified compose | `infra/docker-compose.yml` |
| Dev port overrides | `infra/docker-compose.override.yml` |
| Environment example | `infra/.env.example` |
| Nginx template | `infra/nginx/nginx.conf.template` |
| PostgreSQL init | `infra/postgres/init/01_create_databases.sql` |
| Integration tests | `integration-tests/` |

## Getting Started

```bash
cp infra/.env.example infra/.env
# Fill in required credentials (POSTGRES_PASSWORD, SECRET_KEY values, OPENAI_API_KEY)
docker compose -f infra/docker-compose.yml up --build
```

## Sibling Project Paths

- `specs/001-monorepo-unification/` — implementation plan and contracts
- `development/` — agent definitions and scripts
- `infra/` — unified Docker Compose and infrastructure
- `integration-tests/` — cross-service test suite

## Canonical Versions

- Python: 3.12 (all services)
- FastAPI: 0.115.5, SQLAlchemy: 2.0.36, asyncpg: 0.30.0, pydantic: 2.10.3
- ruff: 0.8.3
- React: 18.3.1, Vite: 6.0.3, Vitest: 2.1.8, Zustand: 5.0.2
- PostgreSQL: 16, MongoDB: 7, Nginx: alpine

See `pyproject.toml [tool.versions]` and `package.json canonicalVersions` for pinned versions.
