# Data Model: GitHub Actions CI/CD Pipeline

**Feature**: 005-github-actions-cicd
**Date**: 2026-06-25

This feature is infrastructure/configuration — there is no application database schema.
All state is ephemeral pipeline state (GitHub Actions job context) or VPS filesystem
state (Docker image tags). This document captures the configuration data structures
and VPS filesystem state model.

---

## Pipeline Configuration Entities

### ServiceMap

Defined in `.github/scripts/detect-changes.sh`. Fixed at design time.

| Service Name (output) | Monitored Paths |
|----------------------|-----------------|
| `uim-backend` | `services/user-input-manager/backend/**` |
| `tm-backend` | `services/ticket-manager/backend/**` |
| `orchestrator` | `services/orchestrator/**` |
| `context-distiller` | `services/context-distiller/**` |
| `agent-dispatcher` | `services/agent-dispatcher/**` |
| `agent-tools` | `services/agent-tools/**` |
| `uim-frontend` | `services/user-input-manager/frontend/**` |
| `tm-frontend` | `services/ticket-manager/frontend/**` |
| `nginx` | `infra/nginx/**` |
| `ALL` | `infra/docker-compose.yml` → triggers all above |
| `NONE` | `infra/.env.example`, `infra/postgres/**`, `specs/**`, `*.md` → no rebuild |

Output format: JSON array of service name strings, e.g. `["tm-backend", "uim-frontend"]`

### ServiceBuildPath

Defined in `.github/scripts/service-to-path.sh`. Maps service name → VPS build context.

| Service Name | VPS Build Path | Docker Compose Service Name |
|---|---|---|
| `uim-backend` | `services/user-input-manager/backend` | `user-input-manager` |
| `tm-backend` | `services/ticket-manager/backend` | `ticket-manager` |
| `orchestrator` | `services/orchestrator` | `orchestrator` |
| `context-distiller` | `services/context-distiller` | `context-distiller` |
| `agent-dispatcher` | `services/agent-dispatcher` | `agent-dispatcher` |
| `agent-tools` | `services/agent-tools` | `agent-tools` |
| `uim-frontend` | `services/user-input-manager/frontend` | `uim-frontend` |
| `tm-frontend` | `services/ticket-manager/frontend` | `tm-frontend` |
| `nginx` | `infra/nginx` | `nginx` |

### Services with Database Migrations (alembic-enabled)

Only these services have PostgreSQL databases requiring Alembic migration steps.
The migration step runs only when these services are in the changed set.

| Service | Compose Service Name | Database |
|---------|---------------------|----------|
| `uim-backend` | `user-input-manager` | `df_user_input` |
| `tm-backend` | `ticket-manager` | `df_ticket_manager` |
| `orchestrator` | `orchestrator` | `df_orchestrator` |
| `context-distiller` | `context-distiller` | `df_distiller` |
| `agent-dispatcher` | `agent-dispatcher` | `df_dispatcher` |

`agent-tools`, `uim-frontend`, `tm-frontend`, `nginx` have NO migration step.

---

## VPS Filesystem State

### Repository

```
/app/dark-factory/
├── infra/
│   ├── docker-compose.yml
│   ├── .env                     ← manually placed; never in git or CI
│   └── ...
├── services/
│   └── ...
└── .github/
    ├── scripts/
    │   ├── detect-changes.sh
    │   └── service-to-path.sh
    └── workflows/
        ├── ci-cd.yml
        └── manual-rollback.yml
```

### Docker Image Tags (VPS-local, no registry)

Each service has exactly two meaningful tag states on the VPS:

| Tag Pattern | Purpose |
|-------------|---------|
| `dark-factory-{service}:latest` | Currently running image |
| `dark-factory-{service}:rollback-{YYYYMMDDHHMMSS}` | Pre-deployment snapshot |

Retention: 3 most recent `rollback-*` tags kept; older tags deleted by the pipeline.

---

## GitHub Actions Secrets (exactly 3)

| Secret Name | Value |
|------------|-------|
| `VPS_HOST` | IP address of the Hetzner VPS |
| `VPS_USER` | SSH username (e.g. `ubuntu`) |
| `VPS_SSH_KEY` | Private SSH key (PEM format) |

No other secrets are permitted.

---

## Certbot Configuration Entity

Added to `infra/docker-compose.yml`:

```yaml
certbot:
  image: certbot/certbot
  profiles: [certbot]
  volumes:
    - letsencrypt:/etc/letsencrypt
    - certbot_www:/var/www/certbot
```

Shared volumes with nginx:
- `letsencrypt` — read-only mount in nginx at `/etc/letsencrypt`
- `certbot_www` — read-only mount in nginx at `/var/www/certbot`

---

## Dockerfile CMD State Changes

Services requiring CMD correction (constitution XXIV violation fix):

| Service | Current (violating) CMD | Required CMD |
|---------|------------------------|--------------|
| `services/orchestrator/Dockerfile` | `sh -c "alembic upgrade head && uvicorn ..."` | `["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]` |
| `services/agent-dispatcher/Dockerfile` | `sh -c "alembic upgrade head && uvicorn ..."` | `["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]` |
| `services/user-input-manager/backend/Dockerfile` | `sh -c "alembic upgrade head && uvicorn ..."` | `["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]` |
| `services/ticket-manager/backend/entrypoint.sh` + Dockerfile | entrypoint.sh runs alembic | Remove entrypoint.sh alembic call; use direct uvicorn CMD |
| `services/agent-tools/Dockerfile` | `uvicorn src.sidecar:app ...` | `["python", "-m", "src.server"]` |
