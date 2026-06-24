# Contract: Keycloak Realm Configuration

**Applies to**: `infra/keycloak/realm-export.json`
**Date**: 2026-06-24

---

## Realm Settings

| Setting | Value |
|---------|-------|
| `realm` | `dark-factory` (fixed per §XVII — never renamed) |
| `enabled` | `true` |
| `registrationAllowed` | `false` (admin-only user creation) |
| `resetPasswordAllowed` | `true` |
| `bruteForceProtected` | `true` |
| `loginWithEmailAllowed` | `true` |
| `duplicateEmailsAllowed` | `false` |
| `sslRequired` | `external` |
| `accessTokenLifespan` | `300` (seconds; default for user tokens) |
| `ssoSessionMaxLifespan` | `36000` (10 hours) |
| `ssoSessionIdleTimeout` | `1800` (30 minutes) |

---

## Realm Roles

| Role | Description |
|------|-------------|
| `user` | Default role assigned to all accounts |
| `administrator` | Grants access to Keycloak Admin Console link in sidebar |

`defaultRoles: ["user"]` — every new user automatically gets the `user` role.

---

## Client Registrations

### uim-frontend (Public, PKCE)
```json
{
  "clientId": "uim-frontend",
  "publicClient": true,
  "standardFlowEnabled": true,
  "directAccessGrantsEnabled": false,
  "attributes": { "pkce.code.challenge.method": "S256" },
  "redirectUris": ["${UIM_FRONTEND_URL}/*"],
  "webOrigins": ["${UIM_FRONTEND_URL}"]
}
```

### tm-frontend (Public, PKCE)
```json
{
  "clientId": "tm-frontend",
  "publicClient": true,
  "standardFlowEnabled": true,
  "directAccessGrantsEnabled": false,
  "attributes": { "pkce.code.challenge.method": "S256" },
  "redirectUris": ["${TM_FRONTEND_URL}/*"],
  "webOrigins": ["${TM_FRONTEND_URL}"]
}
```

### oauth2-proxy (Confidential)
```json
{
  "clientId": "oauth2-proxy",
  "publicClient": false,
  "secret": "${OAUTH2_PROXY_CLIENT_SECRET}",
  "standardFlowEnabled": false,
  "serviceAccountsEnabled": false
}
```

### orchestrator (Confidential, Service Account)
```json
{
  "clientId": "orchestrator",
  "publicClient": false,
  "secret": "${KC_ORCHESTRATOR_CLIENT_SECRET}",
  "serviceAccountsEnabled": true,
  "attributes": { "access.token.lifespan": "3600" }
}
```

### context-distiller (Confidential, Service Account)
```json
{
  "clientId": "context-distiller",
  "publicClient": false,
  "secret": "${KC_DISTILLER_CLIENT_SECRET}",
  "serviceAccountsEnabled": true,
  "attributes": { "access.token.lifespan": "3600" }
}
```

### agent-dispatcher (Confidential, Service Account, 1h TTL)
```json
{
  "clientId": "agent-dispatcher",
  "publicClient": false,
  "secret": "${KC_DISPATCHER_CLIENT_SECRET}",
  "serviceAccountsEnabled": true,
  "attributes": { "access.token.lifespan": "3600" }
}
```

### agent-tools (Confidential, Service Account)
```json
{
  "clientId": "agent-tools",
  "publicClient": false,
  "secret": "${KC_AGENT_TOOLS_CLIENT_SECRET}",
  "serviceAccountsEnabled": true,
  "attributes": { "access.token.lifespan": "3600" }
}
```

### user-input-manager (Confidential, Service Account)
```json
{
  "clientId": "user-input-manager",
  "publicClient": false,
  "secret": "${KC_UIM_CLIENT_SECRET}",
  "serviceAccountsEnabled": true,
  "attributes": { "access.token.lifespan": "3600" }
}
```

### ticket-manager (Confidential, Service Account)
```json
{
  "clientId": "ticket-manager",
  "publicClient": false,
  "secret": "${KC_TM_CLIENT_SECRET}",
  "serviceAccountsEnabled": true,
  "attributes": { "access.token.lifespan": "3600" }
}
```

---

## Google Identity Provider Placeholder

```json
{
  "alias": "google",
  "displayName": "Google",
  "providerId": "google",
  "enabled": false,
  "trustEmail": true,
  "config": {
    "clientId": "${GOOGLE_CLIENT_ID}",
    "clientSecret": "${GOOGLE_CLIENT_SECRET}",
    "defaultScope": "openid email profile",
    "useJwksUrl": "true"
  }
}
```

`enabled: false` is the default. To enable: set `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET`
in `.env` and edit the realm definition (or via Admin Console).

---

## Bootstrap Admin User

```json
{
  "username": "${KC_BOOTSTRAP_ADMIN_USERNAME}",
  "email": "${KC_BOOTSTRAP_ADMIN_EMAIL}",
  "enabled": true,
  "emailVerified": true,
  "realmRoles": ["administrator", "user"],
  "credentials": [{
    "type": "password",
    "value": "${KC_BOOTSTRAP_ADMIN_PASSWORD}",
    "temporary": true
  }]
}
```

`temporary: true` means the admin is prompted to change the password on first login.

---

## Environment Variables Required (new additions to .env.example)

```dotenv
# Keycloak bootstrap admin
KC_BOOTSTRAP_ADMIN_USERNAME=admin
KC_BOOTSTRAP_ADMIN_EMAIL=admin@dark-factory.local
KC_BOOTSTRAP_ADMIN_PASSWORD=changeme_kc_admin   # REQUIRED — change before deploying

# Keycloak database user
KC_DB_USERNAME=keycloak_user
KC_DB_PASSWORD=changeme_kc_db                   # REQUIRED

# Keycloak hostname (how nginx/external clients reach it)
KC_HOSTNAME=localhost                           # localhost for dev; public domain for prod

# oauth2-proxy secrets
OAUTH2_PROXY_CLIENT_SECRET=changeme             # REQUIRED — must match realm client secret
OAUTH2_PROXY_COOKIE_SECRET=changeme-32-bytes!!  # REQUIRED — 32-char random string

# Service client secrets (confidential Keycloak clients)
KC_ORCHESTRATOR_CLIENT_SECRET=changeme_orch
KC_DISTILLER_CLIENT_SECRET=changeme_distiller
KC_DISPATCHER_CLIENT_SECRET=changeme_dispatcher
KC_AGENT_TOOLS_CLIENT_SECRET=changeme_agent_tools
KC_UIM_CLIENT_SECRET=changeme_uim
KC_TM_CLIENT_SECRET=changeme_tm

# Google OIDC (disabled by default; leave empty)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Frontend URLs (for Keycloak redirect URIs in realm)
UIM_FRONTEND_URL=http://localhost:5173          # dev; use ${UIM_HOST} in prod
TM_FRONTEND_URL=http://localhost:5174           # dev; use ${TM_HOST} in prod

# Frontend env vars (Vite)
VITE_KEYCLOAK_URL=http://localhost:8080
VITE_KEYCLOAK_REALM=dark-factory
VITE_UIM_CLIENT_ID=uim-frontend
VITE_TM_CLIENT_ID=tm-frontend
```

---

## substitute-env.sh Contract

```bash
#!/bin/bash
set -e
INPUT="/opt/keycloak/data/import/realm-export.json"
OUTPUT="/opt/keycloak/data/import/realm.json"
envsubst < "$INPUT" > "$OUTPUT"
echo "[Keycloak] Realm JSON substituted → $OUTPUT"
```

Must be mounted at the same path and run before `kc.sh start`. Mount both files in compose:
```yaml
volumes:
  - ./keycloak/realm-export.json:/opt/keycloak/data/import/realm-export.json:ro
  - ./keycloak/substitute-env.sh:/opt/keycloak/data/import/substitute-env.sh:ro
```
Entrypoint override in docker-compose:
```yaml
entrypoint: >
  /bin/bash -c "
    chmod +x /opt/keycloak/data/import/substitute-env.sh &&
    /opt/keycloak/data/import/substitute-env.sh &&
    /opt/keycloak/bin/kc.sh start
    --import-realm
    --db=postgres
    --db-url=jdbc:postgresql://postgres:5432/keycloak
    --db-username=${KC_DB_USERNAME}
    --db-password=${KC_DB_PASSWORD}
    --hostname=${KC_HOSTNAME}
    --hostname-strict=false
    --http-enabled=true
    --proxy=edge
    --log-level=INFO"
```
