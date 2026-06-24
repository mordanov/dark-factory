# Code Review: Phase 1 — Keycloak Infra Setup

**Feature**: 004-keycloak-iam-migration  
**Phase**: 1 (T001–T006)  
**Reviewer**: code-reviewer agent  
**Date**: 2026-06-24  
**Scope**: `infra/keycloak/realm-export.json`, `infra/keycloak/substitute-env.sh`,
`infra/oauth2-proxy/config.cfg`, `infra/docker-compose.yml` (keycloak + oauth2-proxy additions),
`infra/postgres/init/01_create_databases.sh`, `infra/nginx/nginx.conf.template`,
`infra/.env.example`

---

## Code Review Result

### Decision

**APPROVED WITH COMMENTS**

Phase 1 infra files are structurally sound and implement the contracts correctly. Two minor
findings require attention; neither is a blocker. One nit on `substitute-env.sh` is noted.

---

### Scope Reviewed

- T001 `realm-export.json` — all 9 client registrations, 2 realm roles, Google IdP placeholder,
  bootstrap admin user, realm settings
- T002 `substitute-env.sh` — envsubst runner
- T003 `oauth2-proxy/config.cfg` — provider, skip_jwt_bearer_tokens, cookie settings
- T004 `docker-compose.yml` — keycloak + oauth2-proxy service definitions, healthchecks,
  `depends_on: keycloak: condition: service_healthy` on all 6 application services
- T005 `postgres/init/01_create_databases.sh` — keycloak database creation
- T006 `infra/.env.example` — auth section additions
- T037 `nginx/nginx.conf.template` — auth_request integration

---

### Summary

- `realm-export.json` matches the contract exactly: all 9 clients registered, PKCE enabled for
  frontend clients, service accounts enabled for backend clients, Google IdP disabled,
  bootstrap admin present with `temporary: true`.
- `docker-compose.yml` correctly sets `AUTH_MODE: keycloak` (never `local`) for all services,
  and all 6 application services depend on `keycloak: condition: service_healthy`. BLK-03 is
  satisfied.
- Keycloak healthcheck polls `/realms/dark-factory` with `interval:15s retries:20
  start_period:60s` — matches contract.
- `nginx.conf.template` correctly implements `auth_request /oauth2/auth` on `/api/` locations;
  `location = /oauth2/auth` is `internal`; `/.well-known/acme-challenge/` is unprotected; SSL
  stanza is present but commented; `$UIM_HOST` and `$TM_HOST` are used (no hardcoded DNS).
- `01_create_databases.sh` creates all required databases including `keycloak`.
- `oauth2-proxy/config.cfg` has `cookie_secure = false` with the required production comment
  (FIND-05 from security review addressed).
- Only `realm-export.json:ro` and `substitute-env.sh:ro` are mounted; no `realm.json` host
  volume (FIND-06 satisfied).

---

### Blockers

None.

---

### Major Findings

None.

---

### Minor Findings

#### Minor: `substitute-env.sh` uses unrestricted `envsubst` — any env var in realm.json is replaced

**Location**: `infra/keycloak/substitute-env.sh:5`  
**Issue**: `envsubst < "$INPUT" > "$OUTPUT"` substitutes ALL environment variables present in
the container, not only the explicitly-declared KC_* variables. If Keycloak or the OS happens
to define an env var whose name coincidentally appears in `realm-export.json` (e.g. `$HOSTNAME`,
`$USER`, `$HOME`), those values will be silently substituted.  
**Impact**: Low risk in practice — the current `realm-export.json` only contains `${KC_*}`,
`${GOOGLE_*}`, `${OAUTH2_*}`, `${UIM_FRONTEND_URL}`, `${TM_FRONTEND_URL}` variables which are
all explicitly set. But the approach is fragile for future template additions.  
**Required action**: Per software-architect recommendation AI-03, restrict substitution to the
explicit variable list:

```bash
envsubst '${KC_BOOTSTRAP_ADMIN_USERNAME} ${KC_BOOTSTRAP_ADMIN_EMAIL} ${KC_BOOTSTRAP_ADMIN_PASSWORD}
  ${OAUTH2_PROXY_CLIENT_SECRET} ${KC_ORCHESTRATOR_CLIENT_SECRET} ${KC_DISTILLER_CLIENT_SECRET}
  ${KC_DISPATCHER_CLIENT_SECRET} ${KC_AGENT_TOOLS_CLIENT_SECRET} ${KC_UIM_CLIENT_SECRET}
  ${KC_TM_CLIENT_SECRET} ${GOOGLE_CLIENT_ID} ${GOOGLE_CLIENT_SECRET}
  ${UIM_FRONTEND_URL} ${TM_FRONTEND_URL}' \
  < "$INPUT" > "$OUTPUT"
```

**Evidence**: Software Architect arch-review AI-03.

---

#### Minor: `infra/.env.example` uses `VITE_UIM_CLIENT_ID`/`VITE_TM_CLIENT_ID` but per-frontend `.env.example` files use `VITE_KEYCLOAK_CLIENT_ID`

**Location**: `infra/.env.example:215,218` vs `services/*/frontend/.env.example:3`  
**Issue**: The global `infra/.env.example` declares `VITE_UIM_CLIENT_ID=uim-frontend` and
`VITE_TM_CLIENT_ID=tm-frontend` (lines 215, 218). However, both `keycloak.ts` files read
`VITE_KEYCLOAK_CLIENT_ID`, and the per-frontend `.env.example` files correctly define
`VITE_KEYCLOAK_CLIENT_ID`. This means the infra env example documents variables that don't
actually match what the code reads.  
**Impact**: Low — the per-frontend `.env.example` files are what developers follow, so runtime
is correct. But the infra example is misleading.  
**Required action**: Update `infra/.env.example` lines 215/218 to replace
`VITE_UIM_CLIENT_ID`/`VITE_TM_CLIENT_ID` with a comment pointing to the per-frontend files,
or add a note explaining that each frontend has its own `VITE_KEYCLOAK_CLIENT_ID`.

---

### Nits

#### Nit: `substitute-env.sh` missing explicit `set -u` (unset variable detection)

**Location**: `infra/keycloak/substitute-env.sh:1`  
**Issue**: Script has `set -e` but not `set -u`. With unrestricted `envsubst`, an unset
variable silently substitutes to empty string rather than failing.  
**Required action**: Optional; addressed if the Major finding above is fixed by switching to
explicit variable list (which inherently makes unset vars fail at docker-compose startup via
the `:?` syntax).

---

### Tests and Evidence Reviewed

- `docker-compose.yml`: `AUTH_MODE: keycloak` confirmed on all 6 services — BLK-03 satisfied.
- `docker-compose.yml`: all required secrets use `:?` syntax (fail-fast if unset).
- `realm-export.json`: `directAccessGrantsEnabled: false` on public clients — correct.
- `realm-export.json`: `standardFlowEnabled: false` on service account clients — correct.
- `realm-export.json`: Google IdP `enabled: false` — correct per spec FR-014.
- `oauth2-proxy/config.cfg`: `pass_access_token = false` — tokens not forwarded to backend,
  only user headers set — correct per contract.
- `nginx.conf.template`: no `auth_request` on `/`, `/oauth2/`, `/.well-known/` — correct.

---

### Untested or Unverified Areas

- Actual Keycloak startup with `--import-realm` was not live-tested; correctness of
  `realm-export.json` structure is validated against the contract only.
- `substitute-env.sh` substitution result for edge-case env var naming conflicts was not
  tested.

---

### Required Follow-Up

| ID | Action | Owner | Priority |
|----|--------|-------|----------|
| R1-01 | Fix `substitute-env.sh` to use explicit variable list | devops | Minor |
| R1-02 | Align `infra/.env.example` VITE client ID variable names | devops | Minor |
