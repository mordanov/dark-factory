# Data Model: Keycloak IAM Migration

**Feature**: 004-keycloak-iam-migration
**Date**: 2026-06-24

This document covers only the schema changes introduced by this migration. Unchanged tables
are not described here.

---

## Schema Changes: user-input-manager (df_user_input)

### Tables DROPPED (irreversible)

**`users`** — entire table dropped:
```
users (id UUID PK, email VARCHAR, password_hash VARCHAR, full_name VARCHAR,
        is_admin BOOL, is_active BOOL, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)
```

### Tables RECREATED (changed FK to TEXT)

**`prompt_sessions`** — `user_id` column type change:

| Column | Before | After |
|--------|--------|-------|
| `user_id` | `UUID NOT NULL REFERENCES users(id)` | `TEXT NOT NULL` (Keycloak sub) |
| All others | unchanged | unchanged |

The `user_id` value is now the Keycloak `sub` claim (a UUID in string form, e.g.
`"a3f1b2c4-..."`). No FK constraint. No local lookup possible or needed.

### Migration descriptor

```
Revision: <auto>
Description: DESTRUCTIVE: drops all user data
Upgrade: drop sessions FK, drop users table, alter sessions.user_id to TEXT NOT NULL
Downgrade: raise NotImplementedError("DESTRUCTIVE: cannot undo user table removal")
```

---

## Schema Changes: ticket-manager (df_ticket_manager)

### Tables DROPPED (irreversible)

**`users`** — entire table dropped:
```
users (id UUID PK, email VARCHAR(255) UNIQUE, password_hash VARCHAR(255),
        role UserRoleEnum, created_at TIMESTAMPTZ, blocked_at TIMESTAMPTZ NULLABLE,
        refresh_tokens relationship)

refresh_tokens (id UUID PK, user_id UUID FK → users.id, token TEXT, ...)
```

### Tables RECREATED / ALTERED

**`tickets`** — `created_by_id` column type change:

| Column | Before | After |
|--------|--------|-------|
| `created_by_id` | `UUID NOT NULL REFERENCES users(id)` | `TEXT NOT NULL` (Keycloak sub) |
| All others | unchanged | unchanged |

**`ticket_assignments`** — `user_id` column type change:

| Column | Before | After |
|--------|--------|-------|
| `user_id` | `UUID NOT NULL REFERENCES users(id)` | `TEXT NOT NULL` (Keycloak sub) |
| All others | unchanged | unchanged |

**`ticket_events`** — `actor_id` column type change:

| Column | Before | After |
|--------|--------|-------|
| `actor_id` | `UUID NOT NULL REFERENCES users(id)` | `TEXT NOT NULL` (Keycloak sub) |
| All others | unchanged | unchanged |

**`progress_updates`** — `user_id` column type change:

| Column | Before | After |
|--------|--------|-------|
| `user_id` | `UUID NOT NULL REFERENCES users(id)` | `TEXT NOT NULL` (Keycloak sub) |
| All others | unchanged | unchanged |

**`refresh_tokens`** — entire table dropped (local session management removed):
```
refresh_tokens (id, user_id, token, created_at, expires_at, revoked_at)
```

### Migration descriptor

```
Revision: <auto>
Description: DESTRUCTIVE: drops all user data
Upgrade:
  1. Alter tickets.created_by_id UUID FK → TEXT NOT NULL
  2. Alter ticket_assignments.user_id UUID FK → TEXT NOT NULL
  3. Alter ticket_events.actor_id UUID FK → TEXT NOT NULL
  4. Alter progress_updates.user_id UUID FK → TEXT NOT NULL
  5. Drop refresh_tokens table
  6. Drop users table
Downgrade: raise NotImplementedError("DESTRUCTIVE: cannot undo user table removal")
```

---

## Infrastructure: New Keycloak Database (keycloak)

New PostgreSQL database managed by Keycloak. No application code accesses it directly.

```sql
-- Added to infra/postgres/init/01_create_databases.sql
CREATE DATABASE keycloak;
CREATE USER keycloak_user WITH PASSWORD '${KC_DB_PASSWORD}';
GRANT ALL PRIVILEGES ON DATABASE keycloak TO keycloak_user;
ALTER DATABASE keycloak OWNER TO keycloak_user;
```

---

## New Python Data Structures (not DB)

### UserClaims (all services, replaces User ORM)

```python
@dataclass
class UserClaims:
    sub: str                    # Keycloak subject (UUID string)
    email: str                  # email claim
    preferred_username: str     # preferred_username claim (fallback: email)
    roles: list[str]            # realm_access.roles list

    @property
    def is_admin(self) -> bool:
        return "administrator" in self.roles
```

Source: `token_payload["realm_access"]["roles"]` — Keycloak standard claim structure.
Never persisted to DB. Lives only in the request lifecycle as a FastAPI dependency result.

---

## New Configuration Fields (all services)

Each service's `Settings` class gains:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `keycloak_base_url` | str | `http://keycloak:8080` | Internal Keycloak URL |
| `keycloak_realm` | str | `dark-factory` | Realm name (fixed per §XVII) |
| `keycloak_client_id` | str | `""` | Service-specific client ID |
| `keycloak_client_secret` | str | `""` | Service-specific client secret |
| `auth_mode` | str | `keycloak` | `keycloak` or `local` (tests only) |
| `test_jwt_secret` | str | `test-secret-do-not-use` | HS256 secret for `AUTH_MODE=local` |

### Removed configuration fields

| Field removed | Present in |
|---------------|------------|
| `jwt_secret_key` | UIM, Orchestrator, Agent-Dispatcher, Agent-Tools |
| `jwt_algorithm` | UIM, Orchestrator, Agent-Dispatcher |
| `access_token_expires_minutes` / `access_token_expire_minutes` | UIM, TM |
| `refresh_token_expires_days` | UIM |
| `service_jwt_expire_hours` | Agent-Dispatcher |
| `secret_key` (JWT) | TM |
| `refresh_token_secret` | TM |
| `initial_admin_email` / `initial_admin_password` | UIM |
| `default_admin_email` / `default_admin_password` | TM |
| `ticket_manager_service_email` / `ticket_manager_service_password` | UIM, Orchestrator |
