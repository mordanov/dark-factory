# Dark Factory

A multi-service AI development platform.

## Services

| Service | Port | Description |
|---------|------|-------------|
| user-input-manager | 8001 | Prompt Studio — React + FastAPI + PostgreSQL |
| ticket-manager | 8002 | Ticket tracking — React + FastAPI + PostgreSQL |
| orchestrator | 8003 | Workflow FSM — FastAPI + PostgreSQL + MongoDB |
| context-distiller | 8004 | Memory compression — FastAPI + PostgreSQL + MongoDB |
| agent-tools | 8005 | MCP server — Python |

## Getting Started

### Prerequisites

- Docker + Docker Compose v2
- `cp infra/.env.example infra/.env` and fill in credentials

### Start the full platform

```bash
cp infra/.env.example infra/.env
# Edit infra/.env — fill in POSTGRES_PASSWORD, all SECRET_KEY values, OPENAI_API_KEY
docker compose -f infra/docker-compose.yml up --build
```

All services start within 60 seconds. Both frontends are accessible via nginx on port 80.

### Local development (per-service)

Each service has its own `docker-compose.yml` for standalone development:

```bash
cd services/user-input-manager
docker compose up --build
```

### Running integration tests

```bash
cp infra/.env.example infra/.env  # if not done already
docker compose -f integration-tests/docker-compose.test.yml up --build -d
pytest integration-tests/ -v
docker compose -f integration-tests/docker-compose.test.yml down -v
```

## Repository Layout

```
dark-factory/
├── services/
│   ├── user-input-manager/    # Prompt Studio (React + FastAPI + PostgreSQL)
│   ├── ticket-manager/        # Ticket tracking (React + FastAPI + PostgreSQL)
│   ├── orchestrator/          # Workflow FSM (FastAPI + PostgreSQL + MongoDB)
│   ├── context-distiller/     # Memory compression (FastAPI + PostgreSQL + MongoDB)
│   └── agent-tools/           # MCP server (Python)
├── infra/
│   ├── docker-compose.yml     # Unified compose
│   ├── docker-compose.override.yml  # Dev port exposure
│   ├── .env.example           # Environment template
│   ├── nginx/                 # Nginx config template + Dockerfile
│   └── postgres/init/         # PostgreSQL init SQL
├── integration-tests/         # Cross-service test suite
├── specs/                     # Feature specifications
├── pyproject.toml             # Canonical Python versions + ruff config
├── package.json               # Canonical frontend versions (reference)
└── .pre-commit-config.yaml    # Root ruff hooks
```

## Code Quality

```bash
# Install pre-commit
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

## Environment Variables

See `infra/.env.example` for all required variables with inline documentation.
