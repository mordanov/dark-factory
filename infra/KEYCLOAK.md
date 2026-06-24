# Keycloak Operations Guide

## First Boot

1. Copy and fill environment file:
   ```bash
   cp infra/.env.example infra/.env
   # Fill in all REQUIRED values — see comments in .env.example
   ```

2. Start the platform:
   ```bash
   docker compose -f infra/docker-compose.yml up --build
   ```

3. Wait for Keycloak to pass its healthcheck (polls `/realms/dark-factory`).
   The healthcheck has `start_period: 60s` and `retries: 20` — allow up to ~5 minutes on first boot.

## Accessing the Admin Console

- **URL**: `http://localhost:8080/admin/dark-factory/console`
- **Username**: value of `KC_BOOTSTRAP_ADMIN_USERNAME` (default: `admin`)
- **Password**: value of `KC_BOOTSTRAP_ADMIN_PASSWORD` (temporary — must be changed on first login)

## Creating Users

1. Open the Admin Console.
2. Go to **Users** → **Add user**.
3. Set **Username**, **Email**, and mark **Email verified**.
4. After saving, go to the **Credentials** tab and set a password (uncheck Temporary unless you want forced change).
5. Go to the **Role mapping** tab and assign realm roles (`user`, `administrator`).

The `user` role is automatically assigned via `defaultRoles`.

## Assigning the Administrator Role

1. Open the Admin Console → **Users** → select user.
2. Go to **Role mapping** → **Assign role**.
3. Select `administrator` from the realm role list.

Users with the `administrator` role see the Keycloak Admin Console link in the Dark Factory sidebar.

## Enabling Google Login

Google IdP is present in the realm but disabled by default (`enabled: false`).

To enable:

1. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `infra/.env`.
2. In the Admin Console: go to **Identity providers** → **google** → set **Client ID** and **Client Secret** → toggle **Enabled**.
3. Alternatively: edit `infra/keycloak/realm-export.json`, set `"enabled": true` in the google IdP entry, and re-import (see "Re-importing the Realm" below).

## Re-importing the Realm

The realm is imported once at first boot. To re-import after a clean start:

1. Stop and remove the postgres volume (destructive — only for dev resets):
   ```bash
   docker compose -f infra/docker-compose.yml down -v
   ```
2. Restart:
   ```bash
   docker compose -f infra/docker-compose.yml up --build
   ```

For production changes, use the Admin Console or Keycloak REST API instead of re-importing.

## Keycloak Ports

Keycloak runs on port `8080` internally (exposed to the `internal` Docker network only).

For local dev access from the browser, add a port mapping in `infra/docker-compose.override.yml`:
```yaml
services:
  keycloak:
    ports:
      - "8080:8080"
```

## Service Client Secrets

Each backend service uses a Keycloak confidential client (Client Credentials grant) for service-to-service tokens.
All client secrets must match between `infra/.env` and the realm configuration.

| Service | Client ID | Env var |
|---------|-----------|---------|
| user-input-manager | `user-input-manager` | `KC_UIM_CLIENT_SECRET` |
| ticket-manager | `ticket-manager` | `KC_TM_CLIENT_SECRET` |
| orchestrator | `orchestrator` | `KC_ORCHESTRATOR_CLIENT_SECRET` |
| context-distiller | `context-distiller` | `KC_DISTILLER_CLIENT_SECRET` |
| agent-dispatcher | `agent-dispatcher` | `KC_DISPATCHER_CLIENT_SECRET` |
| agent-tools | `agent-tools` | `KC_AGENT_TOOLS_CLIENT_SECRET` |
| oauth2-proxy | `oauth2-proxy` | `OAUTH2_PROXY_CLIENT_SECRET` |

## AUTH_MODE

`AUTH_MODE=local` (with HS256 HMAC test tokens) is reserved for automated tests only.
It must **never** appear in `infra/docker-compose.yml` — all compose services run with `AUTH_MODE=keycloak`.

## JWKS Caching

Each backend's `KeycloakValidator` caches the JWKS endpoint response for ≥300 seconds.
On cache miss or failure, the last valid JWKS is used with a warning log — the service does not crash.

## Token Lifespans

| Token type | Lifespan |
|------------|----------|
| User access token (realm default) | 300s (5 min) |
| Service account token (CC grant) | 3600s (1 hour) |
| SSO session max | 36000s (10 hours) |
| SSO session idle timeout | 1800s (30 min) |

## Troubleshooting

**Keycloak fails to start**: Check `docker logs keycloak` for DB connectivity errors.
Ensure `KC_DB_PASSWORD` in `.env` matches `KC_DB_PASSWORD` used by the postgres init script.

**`curl -sf http://localhost:8080/realms/dark-factory` returns 404**: Realm import failed.
Check keycloak logs for `realm-export.json` parse errors — usually a malformed `${VAR}` substitution.

**oauth2-proxy returns 401 for valid tokens**: Ensure `OAUTH2_PROXY_CLIENT_SECRET` matches the
`oauth2-proxy` client secret in the Keycloak realm. Restart oauth2-proxy after any secret change.

**Services can't reach Keycloak**: Ensure all services are on the `internal` Docker network.
Keycloak is reachable at `http://keycloak:8080` from within the internal network.
