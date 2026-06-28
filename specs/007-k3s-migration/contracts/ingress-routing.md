# Contract: Ingress Routing

**Ingress Class**: `nginx` (NGINX Ingress Controller)
**TLS**: cert-manager ClusterIssuer `letsencrypt-prod`

## Application Routes

| Hostname | Backend Service | Port | Auth |
|----------|----------------|------|------|
| `studio.dark-factory.local` | `uim-frontend` | 80 | None (keycloak-js client-side) |
| `tickets.dark-factory.local` | `tm-frontend` | 80 | None (keycloak-js client-side) |

### API auth_request (applies to all `/api/*` paths under both hostnames)

All requests to `/api/*` are validated by oauth2-proxy before reaching the backend service. This preserves Principle IX semantics at the Ingress level.

```yaml
nginx.ingress.kubernetes.io/auth-url: "http://oauth2-proxy.dark-factory.svc.cluster.local:4180/oauth2/auth"
nginx.ingress.kubernetes.io/auth-response-headers: "X-Auth-Request-User,X-Auth-Request-Email,X-Auth-Request-Groups"
```

Frontend routes (`/`, `/static/*`, `/*.js`, `/*.css`) do NOT have `auth-url` — keycloak-js handles login redirects in the browser.

## Monitoring Routes

| Hostname | Backend Service | Namespace | Auth |
|----------|----------------|-----------|------|
| `grafana.dark-factory.local` | `kube-prometheus-stack-grafana` | `monitoring` | Basic auth (nginx annotation) |

## TLS Certificates

| Secret Name | Namespace | Covers |
|-------------|-----------|--------|
| `dark-factory-tls` | `dark-factory` | `studio.dark-factory.local`, `tickets.dark-factory.local` |
| `grafana-tls` | `monitoring` | `grafana.dark-factory.local` |

Certificates are provisioned automatically by cert-manager when the Ingress resources are applied, provided DNS resolves the hostnames to the VPS IP.

## DNS Requirements

Before applying production Ingress resources, the following DNS A records must exist:

| Hostname | Points to |
|----------|-----------|
| `studio.dark-factory.local` | VPS public IP |
| `tickets.dark-factory.local` | VPS public IP |
| `grafana.dark-factory.local` | VPS public IP |
