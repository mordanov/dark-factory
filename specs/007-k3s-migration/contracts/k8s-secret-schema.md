# Contract: Kubernetes Secret Schema

**Resource**: `dark-factory-secrets` | **Namespace**: `dark-factory`
**Creation**: Manual — `kubectl create secret generic dark-factory-secrets --from-env-file=infra/.env -n dark-factory`

All keys from `infra/.env` are projected into the Secret. Services consume them via `envFrom.secretRef`. Key names are identical to Docker Compose env var names — no renaming required.

## Required Keys

### PostgreSQL

| Key | Consumed By |
|-----|------------|
| `POSTGRES_USER` | postgres StatefulSet |
| `POSTGRES_PASSWORD` | postgres StatefulSet |
| `UIM_DB_USER` | postgres init, user-input-manager |
| `UIM_DB_PASSWORD` | postgres init, user-input-manager |
| `TM_DB_USER` | postgres init, ticket-manager |
| `TM_DB_PASSWORD` | postgres init, ticket-manager |
| `ORCH_DB_USER` | postgres init, orchestrator |
| `ORCH_DB_PASSWORD` | postgres init, orchestrator |
| `DISTILLER_DB_USER` | postgres init, context-distiller |
| `DISTILLER_DB_PASSWORD` | postgres init, context-distiller |
| `DISPATCHER_DB_USER` | postgres init, agent-dispatcher |
| `DISPATCHER_DB_PASSWORD` | postgres init, agent-dispatcher |

### Keycloak

| Key | Consumed By |
|-----|------------|
| `KC_DB_USERNAME` | keycloak Deployment |
| `KC_DB_PASSWORD` | keycloak Deployment |
| `KC_BOOTSTRAP_ADMIN_USERNAME` | keycloak Deployment |
| `KC_BOOTSTRAP_ADMIN_PASSWORD` | keycloak Deployment |
| `KC_BOOTSTRAP_ADMIN_EMAIL` | keycloak Deployment |
| `KC_HOSTNAME` | keycloak Deployment |
| `OAUTH2_PROXY_CLIENT_SECRET` | oauth2-proxy Deployment |
| `OAUTH2_PROXY_COOKIE_SECRET` | oauth2-proxy Deployment |
| `KC_ORCHESTRATOR_CLIENT_SECRET` | orchestrator Deployment |
| `KC_DISTILLER_CLIENT_SECRET` | context-distiller Deployment |
| `KC_DISPATCHER_CLIENT_SECRET` | agent-dispatcher Deployment |
| `KC_AGENT_TOOLS_CLIENT_SECRET` | agent-tools Deployment |
| `KC_UIM_CLIENT_SECRET` | user-input-manager Deployment |
| `KC_TM_CLIENT_SECRET` | ticket-manager Deployment |

### Application / AI

| Key | Consumed By |
|-----|------------|
| `OPENAI_API_KEY` | user-input-manager, orchestrator, context-distiller, agent-dispatcher |
| `OPENAI_BASE_URL` | same as above |
| `GOOGLE_CLIENT_ID` | keycloak Deployment (realm env substitution) |
| `GOOGLE_CLIENT_SECRET` | keycloak Deployment (realm env substitution) |

### Frontend URLs

| Key | Consumed By |
|-----|------------|
| `UIM_FRONTEND_URL` | backend services (CORS, redirect URIs) |
| `TM_FRONTEND_URL` | backend services |
| `UIM_HOST` | nginx Ingress (via ConfigMap if needed) |
| `TM_HOST` | nginx Ingress (via ConfigMap if needed) |

## Validation

Before `kubectl apply -f k8s/`, verify the Secret contains all required keys:
```bash
kubectl get secret dark-factory-secrets -n dark-factory -o jsonpath='{.data}' | jq 'keys'
```

The Secret must not appear in any committed file. It is populated manually by the operator from the VPS-resident `infra/.env`.
