# Dark Factory — VPS Deployment & CI/CD Constitution

## Identity

This constitution governs the automated deployment of Dark Factory
to a single Hetzner VPS running Ubuntu 24.04 LTS.

The pipeline has three mandatory stages that run in sequence:
`validate → test → deploy`. A failure at any stage aborts the pipeline.
Deployment is triggered on every push to `main`.

There is no staging environment. Local development → `main` → production.

---

## Core Principles

### 1. Build on VPS, not in CI

Docker images are built on the VPS, not in GitHub Actions runners.
The CI runner validates and tests code, then SSHs to the VPS to build
and deploy. There is no container registry.

This means:
- No `docker login` step in CI
- No registry credentials
- VPS must have sufficient CPU/RAM to build all services
- Build artifacts (images) exist only on the VPS

### 2. Path-based change detection

Not every push rebuilds everything. The pipeline detects which services
changed and operates only on those. This reduces build time and
minimises downtime surface.

**Change → Service mapping (fixed, do not add exceptions):**

| Changed path | Services affected |
|---|---|
| `services/user-input-manager/backend/**` | `backend` |
| `services/user-input-manager/frontend/**` | `frontend` |
| `services/ticket-manager/backend/**` | `tm-backend` |
| `services/ticket-manager/frontend/**` | `tm-frontend` |
| `services/orchestrator/**` | `orchestrator` |
| `services/context-distiller/**` | `context-distiller` |
| `services/agent-dispatcher/**` | `agent-dispatcher` |
| `services/agent-tools/**` | `agent-tools` |
| `infra/nginx/**` | `nginx` |
| `infra/keycloak/**` | `keycloak` |
| `infra/docker-compose.yml` | ALL services |
| `infra/.env.example` | No deployment (docs only) |
| `infra/postgres/**` | No deployment (manual migration only) |

If `infra/docker-compose.yml` changes, all services are rebuilt and redeployed.
This is the safe default when infrastructure changes.

### 3. Migrations run before containers restart

`alembic upgrade head` is NOT in any Dockerfile CMD.
Migrations run as a separate `docker compose run --rm` step in the pipeline
AFTER building the new image but BEFORE `docker compose up -d`.

If migration fails: pipeline aborts, old containers keep running.
No partial state. No data corruption.

### 4. Automatic rollback on healthcheck failure

Before deploying, the pipeline snapshots current running image IDs.
After `docker compose up -d`, it waits up to 90 seconds for all
deployed services to pass their healthchecks.

If any healthcheck fails: the pipeline automatically restores the
snapshot images and runs `docker compose up -d` again with the old images.
A GitHub Actions failure notification marks the pipeline as failed.

Rollback mechanism uses `docker tag`:
```bash
# Before deploy: tag current images as backup
docker tag ghcr.io/.../backend:current backend:rollback-$(date +%s)

# After healthcheck failure:
docker tag backend:rollback-{timestamp} backend:current
docker compose up -d {failed_service}
```

### 5. Secrets live on VPS, not in CI

The production `.env` file is manually placed at `/app/dark-factory/infra/.env`
on the VPS. It is never committed to git and never passed through GitHub Actions.

GitHub Actions Secrets contain only:
- `VPS_HOST` — IP address of the Hetzner VPS
- `VPS_USER` — SSH username (ubuntu)
- `VPS_SSH_KEY` — private SSH key for deployment user

Nothing else. No database passwords, no API keys, no client secrets in CI.

### 6. Validation gates (fail fast)

The validate stage runs entirely in CI (no VPS access needed):
- `ruff check` and `ruff format --check` for every changed Python service
- `docker build --no-cache` for every changed service (catches Dockerfile syntax errors)

TypeScript type checking is NOT in the validate stage (too slow for CI,
covered by local development workflow). It runs as part of `npm run build`
inside the Docker build step.

### 7. Tests run in CI with SQLite and AUTH_MODE=local

All tests run in GitHub Actions runners, not on VPS.
No real PostgreSQL, MongoDB, or Keycloak in CI.
- Python backends: SQLite in-memory via aiosqlite
- MongoDB: mongomock-motor
- Auth: AUTH_MODE=local with test JWT secret
- All external HTTP calls: mocked via respx or AsyncMock

Tests must complete within 10 minutes total.
Individual service test timeout: 3 minutes.

---

## Pipeline Structure

```
.github/
├── workflows/
│   ├── ci-cd.yml          ← main pipeline (push to main)
│   └── manual-rollback.yml ← workflow_dispatch for emergency rollback
└── scripts/
    └── detect-changes.sh  ← outputs JSON array of changed services
```

### `ci-cd.yml` jobs

```
push to main
    │
    ├── [job: detect]
    │   outputs: changed_services (JSON array)
    │
    ├── [job: validate] (matrix over changed_services)
    │   ├── ruff check + ruff format --check (Python services)
    │   └── docker build --no-cache (all changed services)
    │
    ├── [job: test] (matrix over changed_services)
    │   ├── pytest --cov (Python backends)
    │   └── vitest run --coverage (frontends)
    │
    └── [job: deploy] (runs on VPS via SSH)
        ├── git pull origin main
        ├── docker compose build {changed}
        ├── [for each changed backend] docker compose run --rm {svc} alembic upgrade head
        ├── docker compose up -d {changed}
        ├── healthcheck loop (90s timeout)
        └── [on failure] rollback + exit 1
```

---

## VPS Directory Structure

```
/app/
└── dark-factory/              ← git clone (deployment user owns this)
    ├── infra/
    │   ├── docker-compose.yml
    │   ├── .env               ← manually placed, never in git
    │   ├── nginx/
    │   ├── keycloak/
    │   ├── oauth2-proxy/
    │   └── postgres/
    └── services/
```

The deployment SSH user (`ubuntu` or dedicated `deploy` user) must have:
- Write access to `/app/dark-factory`
- Permission to run `docker` commands (member of `docker` group)
- No `sudo` required

---

## Certbot

### Container in docker-compose

```yaml
certbot:
  image: certbot/certbot:latest
  restart: no
  volumes:
    - certbot_certs:/etc/letsencrypt
    - certbot_www:/var/www/certbot
  profiles:
    - certbot    # only starts when explicitly called
```

`profiles: [certbot]` means certbot never starts automatically with
`docker compose up`. It only runs when called explicitly:

```bash
# First-time certificate acquisition (run manually on VPS):
docker compose --profile certbot run --rm certbot certonly \
  --webroot --webroot-path=/var/www/certbot \
  -d studio.dark-factory.ru \
  -d tickets.dark-factory.ru \
  --email admin@dark-factory.ru \
  --agree-tos --non-interactive

# Renewal (VPS cron):
0 2 * * * cd /app/dark-factory/infra && \
  docker compose --profile certbot run --rm certbot renew --quiet && \
  docker compose kill -s HUP nginx 2>&1 | logger -t certbot-renewal
```

### nginx SSL configuration

`nginx.conf.template` must include both HTTP and HTTPS server blocks.
The HTTPS block is conditional — nginx starts cleanly even if certs don't
exist yet (HTTP-only mode), then gains HTTPS after certbot runs.

Approach: two template files, selected by `NGINX_ENABLE_SSL` env var:
- `nginx.conf.template` — HTTP only (default, `NGINX_ENABLE_SSL=false`)
- `nginx-ssl.conf.template` — HTTP redirect + HTTPS (set after certbot)

Nginx entrypoint script selects the correct template on startup.

### certbot volumes mounted to nginx

```yaml
nginx:
  volumes:
    - ./nginx/nginx.conf.template:/etc/nginx/templates/default.conf.template:ro
    - certbot_certs:/etc/letsencrypt:ro
    - certbot_www:/var/www/certbot:ro
```

---

## Dockerfile Changes (all backend services)

Remove `alembic upgrade head` from every backend service CMD.

**Before:**
```dockerfile
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port XXXX --workers 1"]
```

**After:**
```dockerfile
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "XXXX", "--workers", "1"]
```

Affected services: user-input-manager, ticket-manager, orchestrator,
context-distiller, agent-dispatcher.

A separate `alembic` stage in each Dockerfile for migration runs:
```dockerfile
# Migration stage (called by pipeline, not at startup)
FROM app AS migrator
CMD ["alembic", "upgrade", "head"]
```

Or simpler: the pipeline uses `docker compose run --rm {service} alembic upgrade head`
which overrides CMD. No additional Dockerfile stage needed.

---

## agent-tools Dockerfile (MCP stdio)

agent-tools has no HTTP server. It runs as a stdio MCP process spawned
by Claude Code via `docker run`. The Dockerfile must support this:

```dockerfile
FROM python:3.12-slim

# git required for gitpython
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Repo is mounted at /repo by the caller
ENV GIT_REPO_PATH=/repo

# MCP stdio process — stdin/stdout is the MCP transport
CMD ["python", "-m", "src.server"]
```

Claude Code MCP config on the machine where agents run:
```json
{
  "mcpServers": {
    "agent-tools": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--volume", "${PROJECT_REPO_PATH}:/repo:ro",
        "--env", "GIT_REPO_PATH=/repo",
        "--env", "DISTILLER_BASE_URL=http://your-vps-ip:8004",
        "dark-factory/agent-tools:latest"
      ]
    }
  }
}
```

agent-tools image is built on VPS as part of the pipeline.
Claude Code pulls it locally via `docker pull` from VPS registry
— OR — developer builds it locally from source (simpler for now).

**For now (Phase 2):** developer runs `docker build` locally when
`services/agent-tools/**` changes. Pipeline builds it on VPS only.
Document this limitation in README.

---

## GitHub Actions Secrets Required

Documented in `infra/DEPLOYMENT.md`:

| Secret name | Value | How to set |
|---|---|---|
| `VPS_HOST` | Hetzner VPS IP | GitHub repo → Settings → Secrets → Actions |
| `VPS_USER` | SSH user (ubuntu) | Same |
| `VPS_SSH_KEY` | Private SSH key content | Same |

To generate SSH key pair for deployment:
```bash
ssh-keygen -t ed25519 -C "dark-factory-deploy" -f ~/.ssh/dark_factory_deploy
# Add public key to VPS: ~/.ssh/authorized_keys
# Add private key content to GitHub Secret VPS_SSH_KEY
```

---

## Initial VPS Setup Script

`infra/scripts/setup-vps.sh` — run once manually, not by pipeline:

```bash
#!/usr/bin/env bash
# Run once on fresh Hetzner VPS:
# ssh ubuntu@VPS_IP "bash -s" < infra/scripts/setup-vps.sh

set -euo pipefail

# Create app directory
sudo mkdir -p /app
sudo chown ubuntu:ubuntu /app

# Clone repo
cd /app
git clone https://github.com/YOUR_ORG/dark-factory.git

# Create .env from example
cp dark-factory/infra/.env.example dark-factory/infra/.env
echo "⚠️  Edit /app/dark-factory/infra/.env before running docker compose up"

# Ensure ubuntu user is in docker group (Docker already installed)
sudo usermod -aG docker ubuntu
echo "Re-login required for docker group to take effect"

echo "✓ VPS setup complete. Next steps:"
echo "  1. Edit /app/dark-factory/infra/.env"
echo "  2. Add GitHub deploy public key to ~/.ssh/authorized_keys"
echo "  3. Push to main to trigger first deployment"
```

---

## manual-rollback.yml

Emergency rollback workflow (workflow_dispatch):

Inputs:
- `service`: which service to rollback (or "all")
- `reason`: text description for audit trail

Action: SSHs to VPS, finds the most recent `rollback-*` tagged image
for the specified service, restores it, and runs `docker compose up -d`.

---

## Definition of Done

1. Push to `main` triggers pipeline automatically
2. `validate` stage catches ruff errors in changed Python services
3. `validate` stage catches Dockerfile syntax errors via `docker build`
4. `test` stage runs unit + integration tests for changed services
5. `test` stage fails if coverage drops below 80% on changed service
6. `deploy` stage SSHs to VPS, builds changed services, runs migrations
7. `deploy` stage waits for healthchecks before marking success
8. On healthcheck failure: automatic rollback restores previous images
9. `docker compose up` does NOT run alembic (migrations are pipeline-only)
10. Certbot container exists in docker-compose with `profiles: [certbot]`
11. nginx starts in HTTP mode; HTTPS enabled after manual certbot run
12. VPS setup script produces a running system when followed
13. `infra/DEPLOYMENT.md` documents all secrets, setup steps, and cron jobs
14. `manual-rollback.yml` workflow exists and is testable via workflow_dispatch

---

## Principles That Must Never Be Violated

- **No secrets in GitHub Actions beyond VPS SSH credentials.**
  Production .env lives on VPS only.
- **Migrations before container restart, never at startup.**
  CMD never contains alembic.
- **Build on VPS.** No registry push from CI runner.
- **Rollback is automatic, not manual.**
  Pipeline handles it without human intervention.
- **Certbot never in the main docker compose up flow.**
  profiles: [certbot] prevents accidental startup.
- **agent-tools has no HTTP server.**
  Its Dockerfile CMD is `python -m src.server` (stdio MCP only).
- **Pipeline must not require sudo on VPS.**
  Deployment user is in docker group.
