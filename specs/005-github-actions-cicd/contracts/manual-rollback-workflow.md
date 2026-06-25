# Contract: .github/workflows/manual-rollback.yml

**Type**: GitHub Actions workflow
**Trigger**: `workflow_dispatch`

## Inputs (workflow_dispatch)

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | choice | yes | Service to roll back, or `all` |
| `reason` | string | yes | Operator-provided reason (appears in audit log) |

Service choices: `uim-backend`, `tm-backend`, `orchestrator`, `context-distiller`,
`agent-dispatcher`, `agent-tools`, `uim-frontend`, `tm-frontend`, `nginx`, `all`

## Behaviour

1. Logs: actor (`${{ github.actor }}`), timestamp, service, reason
2. SSH to VPS:
   - For each target service: `docker tag dark-factory-{service}:rollback-{LATEST} dark-factory-{service}:latest`
   - `docker compose -f infra/docker-compose.yml up -d {service(s)}`
3. Exits 0 on success, 1 if rollback tag not found (logs warning, continues for other services in `all` case)

## Audit Output

The GitHub Actions job log provides the full audit trail:
- Workflow run URL (permanent link)
- `github.actor` — who triggered
- Inputs used — service + reason
- Timestamps are GitHub-provided per step

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All targeted services restored |
| 1 | At least one service had no rollback tag available |
