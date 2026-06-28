# Contract: CI/CD Deploy Stage Interface

**File**: `.github/workflows/ci-cd.yml` — `deploy` job only
**Stages unchanged**: `detect`, `validate`, `test`

## Secrets Required

| Secret Name | Type | Purpose | Replaces |
|-------------|------|---------|---------|
| `KUBECONFIG` | base64-encoded kubeconfig | kubectl cluster access | `VPS_HOST` + `VPS_USER` + `VPS_SSH_KEY` |
| `GHCR_TOKEN` | GitHub PAT (write:packages) | `docker push ghcr.io` | — (new) |

**Secrets to remove after migration**: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`

## Image Naming Convention

```
ghcr.io/${{ github.repository_owner }}/<service-name>:${{ github.sha }}
```

Service names match Docker Compose service names: `user-input-manager`, `ticket-manager`, `orchestrator`, `context-distiller`, `agent-tools`, `agent-dispatcher`, `uim-frontend`, `tm-frontend`.

## Deploy Stage Steps (per changed service)

```
1. echo "$KUBECONFIG" | base64 -d > ~/.kube/config
2. echo "$GHCR_TOKEN" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
3. For each changed service:
   a. docker build -t ghcr.io/<owner>/<service>:${{ github.sha }} services/<service>/
   b. docker push ghcr.io/<owner>/<service>:${{ github.sha }}
   c. [if DB-backed Python service]:
      kubectl run alembic-<service>-<sha> \
        --image=ghcr.io/<owner>/<service>:${{ github.sha }} \
        --rm --restart=Never -n dark-factory \
        --env-from=secret/dark-factory-secrets \
        -- alembic upgrade head
   d. kubectl set image deployment/<service> <container>=ghcr.io/<owner>/<service>:${{ github.sha }} \
        -n dark-factory
   e. kubectl rollout status deployment/<service> -n dark-factory --timeout=120s
      → on failure: kubectl rollout undo deployment/<service> -n dark-factory && exit 1
```

## DB-Backed Python Services (require Alembic step)

- `user-input-manager`
- `ticket-manager`
- `orchestrator`
- `context-distiller`
- `agent-dispatcher`

`agent-tools` has no database — skip Alembic step.

## Rollout Success Criteria

`kubectl rollout status deployment/<service> -n dark-factory --timeout=120s` exits 0.

## Rollback Trigger

`kubectl rollout status` exits non-zero (timeout or pod failure). Rollback runs immediately:
```bash
kubectl rollout undo deployment/<service> -n dark-factory
```
Pipeline exits 1 after rollback completes.

## What Does NOT Change

- `detect` job: `detect-changes.sh` and `service-to-path.sh` unchanged
- `validate` job: ruff + docker build (no push) unchanged
- `test` job: pytest + vitest unchanged
- Per-service Dockerfile contents: unchanged (no `alembic upgrade head` in CMD — Principle XXIV)
