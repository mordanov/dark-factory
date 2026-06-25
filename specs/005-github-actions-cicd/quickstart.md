# Quickstart: GitHub Actions CI/CD Pipeline

**Feature**: 005-github-actions-cicd
**Audience**: Developer onboarding + acceptance test guide

---

## First-Time VPS Setup

```bash
# On the VPS (Ubuntu 24.04):
bash /app/dark-factory/infra/scripts/setup-vps.sh

# Place the production .env file:
cp /path/to/your.env /app/dark-factory/infra/.env
```

## GitHub Secrets Configuration

In the repository → Settings → Secrets → Actions, add exactly:

| Secret | Value |
|--------|-------|
| `VPS_HOST` | VPS IP address |
| `VPS_USER` | `ubuntu` |
| `VPS_SSH_KEY` | Contents of `~/.ssh/id_ed25519` (deployment key) |

**Nothing else.** No database passwords, no Keycloak secrets, no API keys.

---

## Scenario 1: Normal deployment (single service)

```bash
# Developer pushes a change to ticket-manager backend
git add services/ticket-manager/backend/src/api/tickets.py
git commit -m "feat: add ticket filter by group"
git push origin main
```

**Expected pipeline behaviour**:

1. `detect` — emits `["tm-backend"]`
2. `validate` — runs ruff on `services/ticket-manager/backend/`, builds Docker image
3. `test` — runs pytest with `AUTH_MODE=local`, checks 80% coverage
4. `deploy` — SSHs to VPS:
   - `git pull`
   - tags current `ticket-manager:latest` as `ticket-manager:rollback-{TIMESTAMP}`
   - `docker compose build ticket-manager`
   - `docker compose run --rm ticket-manager alembic upgrade head`
   - `docker compose up -d ticket-manager`
   - waits for `/health` to return 200 (up to 90s)
5. Pipeline exits green. `ticket-manager` runs new version on VPS.

**Total time**: ~6–8 minutes.

---

## Scenario 2: Documentation-only push

```bash
git add specs/005-github-actions-cicd/spec.md
git commit -m "docs: update spec"
git push origin main
```

**Expected pipeline behaviour**:

1. `detect` — emits `[]`
2. `validate` — skipped (condition: `has_changes == 'true'` fails)
3. `test` — skipped
4. `deploy` — skipped
5. Pipeline exits green immediately (≈30 seconds).

---

## Scenario 3: Full rebuild (compose file changed)

```bash
git add infra/docker-compose.yml
git commit -m "chore: add resource limits to services"
git push origin main
```

**Expected pipeline behaviour**:

1. `detect` — emits all 9 services
2. `validate` — ruff + docker build for all 9 services (parallel matrix)
3. `test` — pytest/vitest for all services (parallel matrix)
4. `deploy` — SSHs to VPS, builds all, migrates all Alembic services, restarts all
5. Pipeline green.

---

## Scenario 4: Automatic rollback on failed deployment

```bash
# Developer pushes a bug that causes a service to crash on startup
git push origin main
```

**Expected pipeline behaviour**:

1–3. `validate` and `test` pass (startup crash is a runtime issue)
4. `deploy`:
   - Snapshot taken: `ticket-manager:rollback-20260625120000`
   - New image built and started
   - `/health` check fails for 90 seconds
   - Pipeline automatically runs:
     - `docker tag ticket-manager:rollback-20260625120000 ticket-manager:latest`
     - `docker compose up -d ticket-manager`
   - Pipeline exits 1 (failure)
5. VPS continues running the previous working version of `ticket-manager`.

---

## Scenario 5: Manual emergency rollback via GitHub UI

1. Navigate to Actions → `manual-rollback` workflow
2. Click "Run workflow"
3. Select service: `tm-backend`
4. Enter reason: `regression in ticket search reported by user`
5. Click "Run workflow"

**Expected outcome**:
- VPS restores `ticket-manager:rollback-{LATEST}` within 2 minutes
- Audit log in the job output shows actor + reason + timestamp

---

## Scenario 6: Concurrent pushes — queue behaviour

Two developers push to `main` within 30 seconds of each other.

**Expected behaviour**:
- First pipeline runs deploy stage normally
- Second pipeline's deploy job waits (GitHub Actions concurrency group: `production`)
- First deploy completes → second deploy starts
- Both deployments complete; no interleaving

---

## SSL Certificate (manual, post-deploy)

```bash
# On VPS, after HTTP is working:
docker compose -f infra/docker-compose.yml --profile certbot run --rm certbot \
  certonly --webroot --webroot-path=/var/www/certbot \
  -d studio.dark-factory.com -d tickets.dark-factory.com \
  --email admin@dark-factory.com --agree-tos

# Then uncomment SSL blocks in infra/nginx/nginx.conf.template and restart nginx
docker compose -f infra/docker-compose.yml restart nginx
```

---

## Checking pipeline status

```bash
# CLI
gh run list --limit 5

# Watch a specific run
gh run watch
```
