# Contract: .github/workflows/ci-cd.yml

**Type**: GitHub Actions workflow
**Trigger**: `push` to `main` branch

## Job Graph

```
detect → validate (matrix) → test (matrix) → deploy
```

All jobs run sequentially. `test` needs `validate` to succeed. `deploy` needs `test`
to succeed. Matrix jobs within `validate` and `test` run in parallel.

## Job: detect

**Runs on**: `ubuntu-latest`

**Outputs**:
- `services`: JSON array string from `detect-changes.sh`
- `has_changes`: `"true"` if array is non-empty, `"false"` otherwise

**Steps**:
1. `actions/checkout@v4` with `fetch-depth: 2`
2. Run `.github/scripts/detect-changes.sh`, capture JSON
3. Set job outputs

## Job: validate

**Needs**: `detect`
**Condition**: `needs.detect.outputs.has_changes == 'true'`
**Strategy**: matrix over `needs.detect.outputs.services`
**Runs on**: `ubuntu-latest`

**Steps per service**:
1. `actions/checkout@v4`
2. Set up Python 3.12 (if Python service)
3. Run `ruff check` and `ruff format --check` (Python services only)
4. Run `docker build --no-cache` for the service (all services)

**Failure**: Any step failing causes the matrix job to fail, which fails `validate`.

## Job: test

**Needs**: `validate`
**Condition**: `needs.detect.outputs.has_changes == 'true'`
**Strategy**: matrix over same service list
**Runs on**: `ubuntu-latest`

**Steps per Python backend service**:
1. `actions/checkout@v4`
2. Set up Python 3.12
3. Install dependencies from `requirements.txt`
4. Run `pytest --cov --cov-fail-under=80` with env:
   - `AUTH_MODE=local`
   - `TEST_JWT_SECRET=ci-test-secret`
   - `DATABASE_URL=sqlite+aiosqlite:///:memory:`
   - `MONGO_URL=mongomock://localhost` (MongoDB services only)
   - `OPENAI_API_KEY=test-key`

**Steps per frontend service**:
1. `actions/checkout@v4`
2. Set up Node.js 20
3. `npm ci`
4. `npm run test -- --run --coverage`

**Failure**: Test failures or coverage below 80% fail the job.

## Job: deploy

**Needs**: `test`
**Condition**: `needs.detect.outputs.has_changes == 'true'`
**Concurrency**: `group: production`, `cancel-in-progress: false`
**Runs on**: `ubuntu-latest`

**Steps**:
1. SSH to VPS: `cd /app/dark-factory && git pull origin main`
2. SSH to VPS: snapshot current images (tag `:rollback-{TIMESTAMP}`)
3. SSH to VPS: `docker compose -f infra/docker-compose.yml build {changed_services}`
4. SSH to VPS: for each migration-enabled changed service:
   `docker compose -f infra/docker-compose.yml run --rm {service} alembic upgrade head`
   — abort entire deploy if any migration fails
5. SSH to VPS: `docker compose -f infra/docker-compose.yml up -d {changed_services}`
6. SSH to VPS: `wait-healthy.sh {changed_services}` — poll /health for 90s
7. If unhealthy: SSH to VPS: restore rollback snapshots + `docker compose up -d`; exit 1

## Secrets Required

```yaml
secrets:
  VPS_HOST:    ${{ secrets.VPS_HOST }}
  VPS_USER:    ${{ secrets.VPS_USER }}
  VPS_SSH_KEY: ${{ secrets.VPS_SSH_KEY }}
```

No other secrets.
