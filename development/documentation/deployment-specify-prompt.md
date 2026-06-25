# /speckit.specify — VPS Deployment & GitHub Actions CI/CD

## Prompt (copy-paste into Claude Code)

```
/speckit.specify

Implement GitHub Actions CI/CD pipeline and VPS deployment configuration
for Dark Factory monorepo on Hetzner VPS (Ubuntu 24.04 LTS).

Three pipeline stages: validate → test → deploy.
Build happens on VPS (no container registry).
Migrations run as a separate pipeline step, not at container startup.
Automatic rollback on healthcheck failure.

Read ALL context files before generating the spec.

## Context files (read in this order)

@.specify/memory/constitution.md
@.specify/memory/service-map.md
@../../infra/docker-compose.yml
@../../infra/.env.example
@../../infra/nginx/nginx.conf.template
@../../services/user-input-manager/backend/Dockerfile
@../../services/user-input-manager/frontend/Dockerfile
@../../services/ticket-manager/backend/Dockerfile
@../../services/orchestrator/Dockerfile
@../../services/context-distiller/Dockerfile
@../../services/agent-dispatcher/Dockerfile
@../../services/agent-tools/Dockerfile

Do not go above the ../../ directory level (monorepo root).

## What to specify

### 1. Change detection script
   (`.github/scripts/detect-changes.sh`)

Bash script that compares `git diff --name-only HEAD~1 HEAD` against
the path mapping table in the constitution.

Output: JSON array of affected docker-compose service names.
Example: `["backend", "orchestrator"]`

Rules:
- Each path prefix maps to one or more service names (from constitution table)
- `infra/docker-compose.yml` change → output ALL service names
- Deduplicate output (if frontend and backend both changed → both appear once)
- Empty array `[]` if only docs or .env.example changed
- Service names must match exactly the `docker-compose.yml` service keys

```bash
#!/usr/bin/env bash
# Usage: ./detect-changes.sh
# Output: JSON array, e.g. ["backend","orchestrator"]
# Requires: git, jq

set -euo pipefail

CHANGED_FILES=$(git diff --name-only HEAD~1 HEAD 2>/dev/null \
  || git diff --name-only HEAD 2>/dev/null)  # fallback for first commit

declare -A SERVICE_MAP=(
  ["services/user-input-manager/backend"]="backend"
  ["services/user-input-manager/frontend"]="frontend"
  ["services/ticket-manager/backend"]="tm-backend"
  ["services/ticket-manager/frontend"]="tm-frontend"
  ["services/orchestrator"]="orchestrator"
  ["services/context-distiller"]="context-distiller"
  ["services/agent-dispatcher"]="agent-dispatcher"
  ["services/agent-tools"]="agent-tools"
  ["infra/nginx"]="nginx"
  ["infra/keycloak"]="keycloak"
)

INFRA_COMPOSE_CHANGED=false
SERVICES=()

while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  
  # docker-compose change → full redeploy
  if [[ "$file" == "infra/docker-compose.yml" ]]; then
    INFRA_COMPOSE_CHANGED=true
    break
  fi
  
  for prefix in "${!SERVICE_MAP[@]}"; do
    if [[ "$file" == "$prefix"* ]]; then
      SERVICES+=("${SERVICE_MAP[$prefix]}")
    fi
  done
done <<< "$CHANGED_FILES"

if [[ "$INFRA_COMPOSE_CHANGED" == "true" ]]; then
  # All services
  ALL=$(docker compose -f infra/docker-compose.yml config --services 2>/dev/null \
    | jq -R . | jq -s .)
  echo "$ALL"
  exit 0
fi

# Deduplicate and output JSON
printf '%s\n' "${SERVICES[@]}" | sort -u | jq -R . | jq -s .
```

### 2. Main CI/CD workflow
   (`.github/workflows/ci-cd.yml`)

```yaml
name: CI/CD

on:
  push:
    branches: [main]

env:
  WORKING_DIR: /app/dark-factory/infra

jobs:
  # ──────────────────────────────────────────────────────────────────
  detect:
    name: Detect changed services
    runs-on: ubuntu-24.04
    outputs:
      services: ${{ steps.detect.outputs.services }}
      has_changes: ${{ steps.detect.outputs.has_changes }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2   # need HEAD~1 for diff

      - name: Detect changes
        id: detect
        run: |
          chmod +x .github/scripts/detect-changes.sh
          SERVICES=$(.github/scripts/detect-changes.sh)
          echo "services=$SERVICES" >> $GITHUB_OUTPUT
          if [[ "$SERVICES" == "[]" ]]; then
            echo "has_changes=false" >> $GITHUB_OUTPUT
          else
            echo "has_changes=true" >> $GITHUB_OUTPUT
          fi
          echo "Changed services: $SERVICES"

  # ──────────────────────────────────────────────────────────────────
  validate:
    name: Validate (${{ matrix.service }})
    needs: detect
    if: needs.detect.outputs.has_changes == 'true'
    runs-on: ubuntu-24.04
    strategy:
      fail-fast: true
      matrix:
        service: ${{ fromJSON(needs.detect.outputs.services) }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        if: contains('["backend","tm-backend","orchestrator","context-distiller","agent-dispatcher","agent-tools"]', matrix.service)
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install ruff
        if: contains('["backend","tm-backend","orchestrator","context-distiller","agent-dispatcher","agent-tools"]', matrix.service)
        run: pip install ruff==0.8.3

      - name: Ruff lint
        if: contains('["backend","tm-backend","orchestrator","context-distiller","agent-dispatcher","agent-tools"]', matrix.service)
        run: |
          SERVICE_PATH=$(.github/scripts/service-to-path.sh ${{ matrix.service }})
          cd "$SERVICE_PATH"
          ruff check src/ tests/

      - name: Ruff format check
        if: contains('["backend","tm-backend","orchestrator","context-distiller","agent-dispatcher","agent-tools"]', matrix.service)
        run: |
          SERVICE_PATH=$(.github/scripts/service-to-path.sh ${{ matrix.service }})
          cd "$SERVICE_PATH"
          ruff format --check src/ tests/

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Docker build (syntax check)
        run: |
          SERVICE_PATH=$(.github/scripts/service-to-path.sh ${{ matrix.service }})
          docker build \
            --file "$SERVICE_PATH/Dockerfile" \
            --tag "dark-factory/${{ matrix.service }}:ci-check" \
            --no-cache \
            "$SERVICE_PATH"

  # ──────────────────────────────────────────────────────────────────
  test:
    name: Test (${{ matrix.service }})
    needs: [detect, validate]
    if: needs.detect.outputs.has_changes == 'true'
    runs-on: ubuntu-24.04
    strategy:
      fail-fast: false    # run all tests even if one fails
      matrix:
        service: ${{ fromJSON(needs.detect.outputs.services) }}
    steps:
      - uses: actions/checkout@v4

      # ── Python backends ──────────────────────────────────────────
      - name: Set up Python 3.12
        if: contains('["backend","tm-backend","orchestrator","context-distiller","agent-dispatcher"]', matrix.service)
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install Python deps
        if: contains('["backend","tm-backend","orchestrator","context-distiller","agent-dispatcher"]', matrix.service)
        run: |
          SERVICE_PATH=$(.github/scripts/service-to-path.sh ${{ matrix.service }})
          pip install -r "$SERVICE_PATH/requirements.txt"

      - name: Run pytest
        if: contains('["backend","tm-backend","orchestrator","context-distiller","agent-dispatcher"]', matrix.service)
        timeout-minutes: 3
        env:
          AUTH_MODE: local
          TEST_JWT_SECRET: test-secret-ci-only
          DATABASE_URL: "sqlite+aiosqlite:///:memory:"
          MONGO_URL: ""          # mongomock-motor used in tests
          OPENAI_API_KEY: "sk-test-not-real"
          KEYCLOAK_BASE_URL: "http://localhost:8080"
          KEYCLOAK_CLIENT_ID: "test-client"
          KEYCLOAK_CLIENT_SECRET: "test-secret"
        run: |
          SERVICE_PATH=$(.github/scripts/service-to-path.sh ${{ matrix.service }})
          cd "$SERVICE_PATH"
          pytest \
            --cov=src \
            --cov-report=term-missing \
            --cov-fail-under=80 \
            -x \
            --timeout=60

      - name: Upload coverage report
        if: contains('["backend","tm-backend","orchestrator","context-distiller","agent-dispatcher"]', matrix.service)
        uses: actions/upload-artifact@v4
        with:
          name: coverage-${{ matrix.service }}
          path: |
            ${{ env.SERVICE_PATH }}/.coverage
            ${{ env.SERVICE_PATH }}/htmlcov/
          retention-days: 7

      # ── Frontends ────────────────────────────────────────────────
      - name: Set up Node.js
        if: contains('["frontend","tm-frontend"]', matrix.service)
        uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: npm
          cache-dependency-path: |
            services/user-input-manager/frontend/package-lock.json
            services/ticket-manager/frontend/package-lock.json

      - name: Install frontend deps
        if: contains('["frontend","tm-frontend"]', matrix.service)
        run: |
          SERVICE_PATH=$(.github/scripts/service-to-path.sh ${{ matrix.service }})
          cd "$SERVICE_PATH"
          npm ci

      - name: Run Vitest
        if: contains('["frontend","tm-frontend"]', matrix.service)
        timeout-minutes: 3
        run: |
          SERVICE_PATH=$(.github/scripts/service-to-path.sh ${{ matrix.service }})
          cd "$SERVICE_PATH"
          npm test

      # ── agent-tools ──────────────────────────────────────────────
      - name: Set up Python for agent-tools
        if: matrix.service == 'agent-tools'
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Test agent-tools
        if: matrix.service == 'agent-tools'
        timeout-minutes: 3
        run: |
          pip install -r services/agent-tools/requirements.txt
          cd services/agent-tools
          pytest --cov=src --cov-fail-under=80 -x

      # ── Infrastructure-only services (nginx, keycloak) ───────────
      # No tests for nginx/keycloak — validation via docker build above

  # ──────────────────────────────────────────────────────────────────
  deploy:
    name: Deploy to VPS
    needs: [detect, validate, test]
    if: needs.detect.outputs.has_changes == 'true'
    runs-on: ubuntu-24.04
    environment: production
    concurrency:
      group: production-deploy
      cancel-in-progress: false   # never cancel in-flight deploy
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.2.0
        env:
          CHANGED_SERVICES: ${{ needs.detect.outputs.services }}
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          timeout: 600s
          script_stop: false   # we handle errors manually for rollback
          envs: CHANGED_SERVICES
          script: |
            set -euo pipefail
            cd /app/dark-factory
            
            # ── 1. Snapshot current state for rollback ──────────────
            TIMESTAMP=$(date +%s)
            ROLLBACK_DIR="/tmp/rollback-$TIMESTAMP"
            mkdir -p "$ROLLBACK_DIR"
            
            SERVICES=$(echo "$CHANGED_SERVICES" | jq -r '.[]')
            for svc in $SERVICES; do
              IMAGE_ID=$(docker compose -f infra/docker-compose.yml \
                inspect "$svc" --format '{{.Image}}' 2>/dev/null || echo "none")
              if [[ "$IMAGE_ID" != "none" && -n "$IMAGE_ID" ]]; then
                docker tag "$IMAGE_ID" "dark-factory-rollback/${svc}:${TIMESTAMP}" \
                  2>/dev/null || true
                echo "$svc:$TIMESTAMP" >> "$ROLLBACK_DIR/manifest"
              fi
            done
            echo "✓ Rollback snapshot saved: $ROLLBACK_DIR"
            
            # ── 2. Pull latest code ─────────────────────────────────
            git fetch origin main
            git reset --hard origin/main
            echo "✓ Code updated to $(git rev-parse --short HEAD)"
            
            # ── 3. Build changed services ───────────────────────────
            cd infra
            BUILD_FAILED=false
            for svc in $SERVICES; do
              echo "Building $svc..."
              if ! docker compose build --no-cache "$svc"; then
                echo "✗ Build failed for $svc"
                BUILD_FAILED=true
                break
              fi
              echo "✓ Built $svc"
            done
            
            if [[ "$BUILD_FAILED" == "true" ]]; then
              echo "Build failed — no containers restarted, old versions still running"
              exit 1
            fi
            
            # ── 4. Run migrations (Python backends only) ────────────
            BACKEND_SERVICES=("backend" "tm-backend" "orchestrator" "context-distiller" "agent-dispatcher")
            MIGRATION_FAILED=false
            
            for svc in $SERVICES; do
              if [[ " ${BACKEND_SERVICES[*]} " =~ " ${svc} " ]]; then
                echo "Running migrations for $svc..."
                if ! docker compose run --rm "$svc" alembic upgrade head; then
                  echo "✗ Migration failed for $svc"
                  MIGRATION_FAILED=true
                  break
                fi
                echo "✓ Migrations complete for $svc"
              fi
            done
            
            if [[ "$MIGRATION_FAILED" == "true" ]]; then
              echo "Migration failed — no containers restarted, old versions still running"
              exit 1
            fi
            
            # ── 5. Restart changed services ─────────────────────────
            docker compose up -d $SERVICES
            echo "✓ Services restarted: $SERVICES"
            
            # ── 6. Healthcheck loop (90s timeout) ───────────────────
            echo "Waiting for healthchecks..."
            DEADLINE=$(($(date +%s) + 90))
            UNHEALTHY_SERVICES=()
            
            while [[ $(date +%s) -lt $DEADLINE ]]; do
              sleep 5
              UNHEALTHY_SERVICES=()
              
              for svc in $SERVICES; do
                STATUS=$(docker compose ps --format json "$svc" 2>/dev/null \
                  | jq -r '.[0].Health // "no-healthcheck"' 2>/dev/null || echo "unknown")
                
                if [[ "$STATUS" == "unhealthy" ]]; then
                  UNHEALTHY_SERVICES+=("$svc")
                elif [[ "$STATUS" == "no-healthcheck" || "$STATUS" == "healthy" ]]; then
                  : # ok
                fi
              done
              
              if [[ ${#UNHEALTHY_SERVICES[@]} -eq 0 ]]; then
                echo "✓ All services healthy"
                break
              fi
              echo "Still waiting... unhealthy: ${UNHEALTHY_SERVICES[*]}"
            done
            
            # ── 7. Rollback if unhealthy ────────────────────────────
            if [[ ${#UNHEALTHY_SERVICES[@]} -gt 0 ]]; then
              echo "✗ Healthcheck timeout. Unhealthy: ${UNHEALTHY_SERVICES[*]}"
              echo "Rolling back..."
              
              if [[ -f "$ROLLBACK_DIR/manifest" ]]; then
                while IFS=: read -r svc ts; do
                  ROLLBACK_IMAGE="dark-factory-rollback/${svc}:${ts}"
                  if docker image inspect "$ROLLBACK_IMAGE" &>/dev/null; then
                    docker tag "$ROLLBACK_IMAGE" "$(docker compose config \
                      --images "$svc" 2>/dev/null | head -1)"
                    docker compose up -d "$svc"
                    echo "  ↩ Rolled back $svc"
                  else
                    echo "  ⚠ No rollback image for $svc"
                  fi
                done < "$ROLLBACK_DIR/manifest"
              fi
              
              # Clean up rollback snapshots older than 3 deploys
              ls -t /tmp/rollback-* 2>/dev/null | tail -n +4 | xargs rm -rf 2>/dev/null || true
              
              exit 1
            fi
            
            # ── 8. Cleanup old rollback snapshots ───────────────────
            ls -t /tmp/rollback-* 2>/dev/null | tail -n +4 | xargs rm -rf 2>/dev/null || true
            echo "✓ Deployment complete: $(git rev-parse --short HEAD)"
```

### 3. Service-to-path helper script
   (`.github/scripts/service-to-path.sh`)

Maps docker-compose service names to filesystem paths:

```bash
#!/usr/bin/env bash
# Usage: service-to-path.sh <service-name>
# Output: relative path to service directory

SERVICE="$1"
case "$SERVICE" in
  backend)           echo "services/user-input-manager/backend" ;;
  frontend)          echo "services/user-input-manager/frontend" ;;
  tm-backend)        echo "services/ticket-manager/backend" ;;
  tm-frontend)       echo "services/ticket-manager/frontend" ;;
  orchestrator)      echo "services/orchestrator" ;;
  context-distiller) echo "services/context-distiller" ;;
  agent-dispatcher)  echo "services/agent-dispatcher" ;;
  agent-tools)       echo "services/agent-tools" ;;
  nginx)             echo "infra/nginx" ;;
  keycloak)          echo "infra/keycloak" ;;
  *)
    echo "Unknown service: $SERVICE" >&2
    exit 1
    ;;
esac
```

### 4. Manual rollback workflow
   (`.github/workflows/manual-rollback.yml`)

```yaml
name: Manual Rollback

on:
  workflow_dispatch:
    inputs:
      service:
        description: Service to rollback (or "all")
        required: true
        type: choice
        options:
          - all
          - backend
          - frontend
          - tm-backend
          - tm-frontend
          - orchestrator
          - context-distiller
          - agent-dispatcher
          - agent-tools
          - nginx
      reason:
        description: Reason for rollback (for audit trail)
        required: true
        type: string

jobs:
  rollback:
    name: Rollback ${{ inputs.service }}
    runs-on: ubuntu-24.04
    environment: production
    steps:
      - name: Execute rollback via SSH
        uses: appleboy/ssh-action@v1.2.0
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          timeout: 120s
          script: |
            set -euo pipefail
            echo "Manual rollback initiated"
            echo "Service: ${{ inputs.service }}"
            echo "Reason: ${{ inputs.reason }}"
            
            # Find most recent rollback snapshot
            LATEST_ROLLBACK=$(ls -t /tmp/rollback-* 2>/dev/null | head -1)
            
            if [[ -z "$LATEST_ROLLBACK" ]]; then
              echo "✗ No rollback snapshots found"
              exit 1
            fi
            
            echo "Using snapshot: $LATEST_ROLLBACK"
            cd /app/dark-factory/infra
            
            SERVICES="${{ inputs.service }}"
            if [[ "$SERVICES" == "all" ]]; then
              SERVICES=$(cat "$LATEST_ROLLBACK/manifest" | cut -d: -f1 | tr '\n' ' ')
            fi
            
            for svc in $SERVICES; do
              TS=$(grep "^${svc}:" "$LATEST_ROLLBACK/manifest" \
                | cut -d: -f2 || echo "")
              if [[ -n "$TS" ]]; then
                ROLLBACK_IMAGE="dark-factory-rollback/${svc}:${TS}"
                if docker image inspect "$ROLLBACK_IMAGE" &>/dev/null; then
                  CURRENT_IMAGE=$(docker compose config --images "$svc" 2>/dev/null | head -1)
                  docker tag "$ROLLBACK_IMAGE" "$CURRENT_IMAGE"
                  docker compose up -d "$svc"
                  echo "✓ Rolled back $svc"
                else
                  echo "✗ Rollback image not found: $ROLLBACK_IMAGE"
                fi
              else
                echo "⚠ No snapshot entry for $svc"
              fi
            done
            
            echo "Manual rollback complete"
            echo "Reason logged: ${{ inputs.reason }}"
```

### 5. Dockerfile changes (all Python backends)

Remove `alembic upgrade head` from CMD in:
- `services/user-input-manager/backend/Dockerfile`
- `services/ticket-manager/backend/Dockerfile` (if present)
- `services/orchestrator/Dockerfile`
- `services/context-distiller/Dockerfile`
- `services/agent-dispatcher/Dockerfile`

Change pattern:
```dockerfile
# Before
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port PORT"]

# After
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "PORT", "--workers", "1"]
```

Each service keeps its own port number.
No other Dockerfile changes.

### 6. agent-tools Dockerfile

Update CMD to MCP stdio mode as specified in constitution:

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser /app
USER appuser

ENV GIT_REPO_PATH=/repo
ENV PYTHONUNBUFFERED=1

# MCP stdio transport — no HTTP server
CMD ["python", "-m", "src.server"]
```

### 7. Certbot in docker-compose

Add to `infra/docker-compose.yml`:

```yaml
  certbot:
    image: certbot/certbot:latest
    restart: no
    profiles:
      - certbot
    volumes:
      - certbot_certs:/etc/letsencrypt
      - certbot_www:/var/www/certbot
    networks:
      - internal
```

Add to volumes section:
```yaml
volumes:
  certbot_certs:
  certbot_www:
```

Update nginx service volumes:
```yaml
  nginx:
    volumes:
      - ./nginx/nginx.conf.template:/etc/nginx/templates/default.conf.template:ro
      - certbot_certs:/etc/letsencrypt:ro
      - certbot_www:/var/www/certbot:ro
```

### 8. nginx.conf.template SSL update

Add `/.well-known/acme-challenge/` location to every server block
(already required by Keycloak constitution, confirming it is here too):

```nginx
# Certbot webroot challenge
location /.well-known/acme-challenge/ {
    root /var/www/certbot;
}
```

Add commented HTTPS server block at the end of each virtual host:

```nginx
# ── HTTPS (uncomment after: docker compose --profile certbot run --rm certbot certonly) ──
# server {
#     listen 443 ssl;
#     server_name ${UIM_HOST};
#
#     ssl_certificate /etc/letsencrypt/live/${UIM_HOST}/fullchain.pem;
#     ssl_certificate_key /etc/letsencrypt/live/${UIM_HOST}/privkey.pem;
#     include /etc/letsencrypt/options-ssl-nginx.conf;
#     ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
#
#     # ... same locations as HTTP block above ...
# }
#
# Redirect HTTP to HTTPS (uncomment together with HTTPS block):
# server {
#     listen 80;
#     server_name ${UIM_HOST};
#     return 301 https://$host$request_uri;
# }
```

### 9. VPS setup script (`infra/scripts/setup-vps.sh`)

Executable bash script, run once manually on fresh VPS:

```bash
#!/usr/bin/env bash
# Dark Factory — One-time VPS setup
# Run: ssh ubuntu@VPS_IP "bash -s" < infra/scripts/setup-vps.sh
# Prerequisites: Docker already installed on VPS

set -euo pipefail

echo "=== Dark Factory VPS Setup ==="

# 1. Create app directory
sudo mkdir -p /app
sudo chown "$USER:$USER" /app
echo "✓ /app directory created"

# 2. Clone repository
cd /app
if [[ ! -d "dark-factory" ]]; then
  git clone https://github.com/YOUR_ORG/dark-factory.git
  echo "✓ Repository cloned"
else
  echo "  Repository already exists, skipping clone"
fi

# 3. Create .env file
if [[ ! -f "dark-factory/infra/.env" ]]; then
  cp dark-factory/infra/.env.example dark-factory/infra/.env
  echo ""
  echo "⚠️  ACTION REQUIRED: Edit the .env file before proceeding:"
  echo "   nano /app/dark-factory/infra/.env"
  echo ""
else
  echo "  .env already exists, skipping"
fi

# 4. Ensure docker group membership
if ! groups | grep -q docker; then
  sudo usermod -aG docker "$USER"
  echo "✓ Added $USER to docker group (re-login required)"
else
  echo "  Already in docker group"
fi

# 5. Create rollback directory
mkdir -p /tmp/rollback-init
echo "✓ Rollback directory ready"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /app/dark-factory/infra/.env (fill in all required values)"
echo "  2. Add GitHub deploy key to ~/.ssh/authorized_keys:"
echo "     echo 'YOUR_PUBLIC_KEY' >> ~/.ssh/authorized_keys"
echo "  3. Re-login for docker group to take effect: exit && ssh ubuntu@$(hostname -I | awk '{print $1}')"
echo "  4. Push to main branch to trigger first deployment"
echo ""
echo "After first successful deployment, set up SSL:"
echo "  cd /app/dark-factory/infra"
echo "  docker compose --profile certbot run --rm certbot certonly \\"
echo "    --webroot --webroot-path=/var/www/certbot \\"
echo "    -d YOUR_DOMAIN --email YOUR_EMAIL --agree-tos --non-interactive"
echo ""
echo "Add certbot renewal to cron:"
echo "  (crontab -l 2>/dev/null; echo '0 2 * * * cd /app/dark-factory/infra && docker compose --profile certbot run --rm certbot renew --quiet && docker compose kill -s HUP nginx 2>&1 | logger -t certbot-renewal') | crontab -"
```

### 10. Deployment documentation (`infra/DEPLOYMENT.md`)

```markdown
# Dark Factory — Deployment Guide

## Architecture

Single Hetzner VPS (Ubuntu 24.04 LTS).
Build happens on VPS. No container registry.
GitHub Actions SSHs to VPS to build and deploy.

## First-Time Setup

### 1. Run setup script
ssh ubuntu@VPS_IP "bash -s" < infra/scripts/setup-vps.sh

### 2. Configure .env
nano /app/dark-factory/infra/.env
Fill in ALL required values. See .env.example for comments.

### 3. Configure GitHub Secrets
Go to: GitHub repo → Settings → Secrets → Actions → New secret

| Secret | Value |
|---|---|
| VPS_HOST | Your Hetzner VPS IP address |
| VPS_USER | ubuntu (or your SSH user) |
| VPS_SSH_KEY | Contents of ~/.ssh/dark_factory_deploy (private key) |

Generate SSH key pair:
ssh-keygen -t ed25519 -C "dark-factory-deploy" -f ~/.ssh/dark_factory_deploy
cat ~/.ssh/dark_factory_deploy.pub >> ~/.ssh/authorized_keys  # on VPS
# Add contents of ~/.ssh/dark_factory_deploy to GitHub Secret VPS_SSH_KEY

### 4. Push to main
git push origin main
Pipeline runs automatically.

## SSL Setup (after first deployment)

cd /app/dark-factory/infra

# Issue certificates
docker compose --profile certbot run --rm certbot certonly \
  --webroot --webroot-path=/var/www/certbot \
  -d studio.dark-factory.ru \
  -d tickets.dark-factory.ru \
  --email admin@dark-factory.ru \
  --agree-tos --non-interactive

# Uncomment HTTPS blocks in nginx.conf.template on VPS
nano nginx/nginx.conf.template

# Restart nginx
docker compose restart nginx

# Add renewal cron (run on VPS)
(crontab -l 2>/dev/null; echo '0 2 * * * cd /app/dark-factory/infra && docker compose --profile certbot run --rm certbot renew --quiet && docker compose kill -s HUP nginx 2>&1 | logger -t certbot-renewal') | crontab -

## Pipeline Stages

### validate
- ruff lint + format check for changed Python services
- docker build (syntax check) for all changed services

### test
- pytest (unit + integration) for Python backends
- vitest for frontends
- Coverage must be ≥ 80%

### deploy
1. git pull origin main
2. docker compose build [changed services]
3. alembic upgrade head [for backend services]
4. docker compose up -d [changed services]
5. healthcheck (90s timeout)
6. rollback if unhealthy

## Manual Rollback

Via GitHub UI: Actions → Manual Rollback → Run workflow
Select service and provide reason.

Or SSH to VPS:
cd /app/dark-factory/infra
ls /tmp/rollback-*         # find available snapshots
# Restore manually using docker tag + docker compose up -d

## agent-tools (MCP Server)

agent-tools has no HTTP endpoint. It runs as a stdio MCP process
spawned by Claude Code. Configure in ~/.claude/mcp_servers.json:

{
  "mcpServers": {
    "agent-tools": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--volume", "/path/to/your/project:/repo:ro",
        "--env", "GIT_REPO_PATH=/repo",
        "--env", "DISTILLER_BASE_URL=http://VPS_IP:8004",
        "dark-factory/agent-tools:latest"
      ]
    }
  }
}

Build locally when agent-tools changes:
cd services/agent-tools
docker build -t dark-factory/agent-tools:latest .
```

### 11. .github directory structure summary

Create ALL of these files:

```
.github/
├── workflows/
│   ├── ci-cd.yml              ← main pipeline
│   └── manual-rollback.yml   ← emergency rollback
└── scripts/
    ├── detect-changes.sh      ← outputs JSON array of changed services
    └── service-to-path.sh     ← maps service name to filesystem path
```

Make scripts executable: `chmod +x .github/scripts/*.sh`

## Constraints (from constitution — enforce all)

- No Docker registry — build on VPS
- No secrets beyond VPS_HOST, VPS_USER, VPS_SSH_KEY in GitHub Actions
- CMD in all backend Dockerfiles contains only uvicorn (no alembic)
- Migrations run via docker compose run --rm BEFORE docker compose up
- Healthcheck timeout is 90 seconds
- Rollback is automatic on healthcheck failure
- certbot uses profiles: [certbot] — never starts with docker compose up
- cancel-in-progress: false on deploy job (never cancel in-flight deploy)
- agent-tools CMD is python -m src.server (no HTTP)
- PATH variable SERVICE_PATH must be set from service-to-path.sh output
- Tests must pass with AUTH_MODE=local and SQLite in-memory

## Out of scope

- HTTPS configuration (manual step after certbot, see DEPLOYMENT.md)
- Hetzner firewall rules (manual: allow 80, 443, 22)
- Monitoring / alerting (Prometheus, Grafana)
- Log aggregation
- Docker Swarm or Kubernetes
- Staging environment
```

---

## Setup

```bash
# From monorepo root
specify init deployment --ai claude

cp /path/to/deployment-constitution.md .specify/memory/constitution.md

cat > .specify/memory/service-map.md << 'EOF'
# Deployment service map

Services in docker-compose:
- backend (user-input-manager FastAPI, port 8001)
- frontend (user-input-manager React, port 80)
- tm-backend (ticket-manager FastAPI, port 8002)
- tm-frontend (ticket-manager React, port 80)
- orchestrator (FastAPI, port 8003)
- context-distiller (FastAPI, port 8004)
- agent-dispatcher (FastAPI, port 8005)
- agent-tools (MCP stdio, no port)
- nginx (reverse proxy, port 80/443)
- postgres (PostgreSQL 16)
- mongo (MongoDB 7)
- keycloak (Keycloak 25, port 8080)
- oauth2-proxy (Bearer validator, port 4180)
- certbot (profiles: certbot, no persistent run)

Python backends with Alembic migrations:
backend, tm-backend, orchestrator, context-distiller, agent-dispatcher
EOF

/speckit.specify  # paste prompt above
```
