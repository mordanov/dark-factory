# Code Review: Phase 5+6+7 — Admin UI Cleanup, Service-to-Service Auth, Destructive Migrations

**Feature**: 004-keycloak-iam-migration  
**Phase**: 5 (T047–T052) + 6 (T053–T063) + 7 (T064–T069)  
**Reviewer**: code-reviewer agent  
**Date**: 2026-06-24  
**Scope**: Admin endpoint/UI deletion, `KeycloakServiceClient` (all 6 services), service caller
migration, destructive Alembic migrations, ORM model text conversion

---

## Code Review Result

### Decision

**APPROVED WITH COMMENTS**

No blockers found. Core `KeycloakServiceClient` implementation is correct and uniform across all 6
services — asyncio.Lock, 30-second refresh buffer, C-KC-04 satisfied, `UpstreamError` on non-200.
Both destructive migrations implement the constitution-mandated `downgrade()` guard. ORM and schema
layers are fully migrated to TEXT user IDs. Two minor consistency issues do not gate merging.

---

### Scope Reviewed

- T047–T048 TM admin endpoints → 410 GONE (confirmed Phase 2)
- T049–T050 Frontend admin routes / Sidebar admin links (confirmed Phase 3+5)
- T051 UIM user_service.py deletion
- T052 UIM users.py router deletion
- T053–T058 `keycloak_client.py` — all 6 services (`KeycloakServiceClient`, `get_kc_client()`)
- T059 Orchestrator `tm_client/client.py` — service token injection
- T060 Agent-dispatcher `reporter.py` — service token injection
- T061 Agent-dispatcher `context_builder.py` — service token injection
- T062 UIM `ticket_manager/client.py` — service token injection
- T063 Agent-dispatcher `core/security.py` deletion
- T064 UIM `alembic/versions/0003_drop_users_table.py`
- T065 TM `alembic/versions/019_drop_users_table.py`
- T066 UIM `models.py` — TEXT user_id
- T067 TM ORM models — TEXT user_id/created_by/actor_id
- T068 UIM `session_service.py` — str user_id
- T069 TM `schemas/ticket.py` — str user_id fields

---

### Summary

**Phase 5 — Admin UI cleanup (T047–T052) — PASS.**

TM admin endpoints return HTTP 410 GONE with pointer to Keycloak Admin Console (verified Phase 2).
Frontend admin routes (`/admin/users`, `/admin/settings`), Sidebar admin links, and `LoginPage`
deletion confirmed in Phase 3+5 review. UIM `user_service.py` absent from
`services/user-input-manager/backend/src/services/` — file deleted. UIM `api/v1/users.py` router
absent from `src/api/v1/` — deleted. No dead import references found.

**Phase 6 — KeycloakServiceClient (T053–T063) — PASS with minor comments.**

All 6 `keycloak_client.py` implementations are functionally identical and correct:

- `asyncio.Lock` double-checked locking before every token use — C-KC-02 satisfied
- 30-second refresh buffer: `time.monotonic() < self._expires_at - 30` — C-KC-01 satisfied
- `UpstreamError` raised on non-200, includes `status_code` and `client_id` but not `client_secret` — C-KC-03 + C-KC-04 satisfied
- `log.debug("keycloak_token_refreshed", client_id=self._client_id)` — no secret logged — C-KC-04 satisfied
- `get_kc_client()` returns a per-service cached singleton via `lru_cache` — correct

Caller migration:
- Orchestrator `tm_client/client.py`: `_login()` removed; `_headers()` → `get_kc_client().async_auth_headers()` — PASS
- Agent-dispatcher `reporter.py`: `{**await get_kc_client().async_auth_headers(), "Content-Type": "application/json"}` — PASS
- Agent-dispatcher `context_builder.py`: injects `## Service Token` block with `await get_kc_client().get_token()` — PASS
- UIM `ticket_manager/client.py`: `return await get_kc_client().async_auth_headers()` — PASS
- Agent-dispatcher `core/security.py` deleted — PASS

Minor inconsistency: `UpstreamError` is imported from `src.core.exceptions` in UIM and orchestrator
(two services that have a shared exceptions module), but defined locally in the other four services
(agent-dispatcher, agent-tools, ticket-manager, context-distiller). The definition is identical in
all cases. Not a blocker — no cross-service import boundary is violated — but consolidation would
reduce drift risk.

Missing tests: `test_keycloak_client.py` exists for UIM, orchestrator, and agent-dispatcher.
Context-distiller, agent-tools, and ticket-manager have no `KeycloakServiceClient` unit tests. The
6-test suite (cold cache, caching, 30s refresh, concurrent Lock, UpstreamError on non-200,
C-KC-04 secret not in error message) should be replicated to those three services.

**Phase 7 — Destructive migrations + ORM migration (T064–T069) — PASS.**

UIM migration `0003_drop_users_table.py`:
- `upgrade()`: adds `user_id_text TEXT`, copies UUID data, enforces NOT NULL, drops FK, drops old
  column, renames — correct multi-step pattern that handles live data safely
- `downgrade()`: `raise NotImplementedError("DESTRUCTIVE: cannot undo user table removal (constitution §XXI)")` — **constitution satisfied**

TM migration `019_drop_users_table.py`:
- `upgrade()`: drops `refresh_tokens`; converts 6 user identity columns across 5 tables
  (tickets.created_by, projects.created_by, ticket_assignments.user_id + assigned_by,
  ticket_events.actor_id, progress_updates.user_id) using the same safe add/UPDATE/NOT NULL/drop
  FK/drop/rename pattern; drops `users` table — correct and thorough
- `downgrade()`: `raise NotImplementedError("DESTRUCTIVE: cannot undo user table removal (constitution §XXI)")` — **constitution satisfied**

ORM models — all PASS:
- TM `user.py`: only `UserRole` enum remains; `User` class deleted
- TM `ticket.py`: `created_by: Mapped[str] = mapped_column(Text, nullable=False)`
- TM `ticket_assignment.py`: both `user_id` and `assigned_by` are `Mapped[str] = mapped_column(Text, ...)`
- TM `ticket_event.py`: `actor_id: Mapped[str] = mapped_column(Text, nullable=False)`
- TM `progress_update.py`: `user_id: Mapped[str] = mapped_column(Text, nullable=False)`
- UIM `models.py`: no `User` class; `PromptSession.user_id: Mapped[str] = mapped_column(Text, nullable=False)`

UIM `session_service.py`: all method signatures use `user_id: str` — PASS.

TM `schemas/ticket.py`: `UserSummary.id: str`, `AssigneeSummary.user_id: str`,
`TicketResponse.created_by: str` — PASS. `AdminUserResponse` in `admin.py` retains UUID fields but
is only served by 410 GONE endpoints with no DB materialization — not a concern.

---

### Minor Findings

#### Minor M7-01: `UpstreamError` defined locally in 4 services instead of imported from `src.core.exceptions`

**Affected services**: agent-dispatcher, agent-tools, ticket-manager, context-distiller  
**Issue**: These four services define `class UpstreamError(Exception): pass` locally in
`keycloak_client.py`. UIM and orchestrator import it from `src.core.exceptions`. The definition is
identical, but if the exception contract changes (e.g., adds a `status_code` attribute), 4 files
will need independent updates.  
**Suggested action**: Add `UpstreamError` to the `src.core.exceptions` module of each affected
service and import it in `keycloak_client.py`. Not required to merge.

#### Minor M7-02: `test_keycloak_client.py` missing in context-distiller, agent-tools, ticket-manager

**Affected services**: context-distiller, agent-tools, ticket-manager  
**Issue**: The 6-test `test_keycloak_client.py` suite (covering cold cache, caching, 30s buffer,
concurrent Lock, UpstreamError on non-200, C-KC-04 secret not in error) exists for UIM,
orchestrator, and agent-dispatcher. The three remaining services have no coverage of
`KeycloakServiceClient`.  
**Suggested action**: Replicate the test file to
`services/{context-distiller,agent-tools,ticket-manager}/tests/unit/test_keycloak_client.py`.
Recommended for the autotester agent.

---

### Passed Checks

| Check | Result | Notes |
|-------|--------|-------|
| TM admin endpoints → 410 GONE | PASS | Verified Phase 2 |
| Frontend admin routes removed | PASS | Verified Phase 3+5 |
| UIM `user_service.py` deleted | PASS | File absent |
| UIM `users.py` API router deleted | PASS | File absent |
| `asyncio.Lock` double-checked locking | PASS | All 6 `keycloak_client.py` |
| 30s refresh buffer (`expires_at - 30`) | PASS | C-KC-01, all 6 |
| `UpstreamError` on non-200 | PASS | C-KC-03, all 6 |
| Client secret not in logs/errors | PASS | C-KC-04, all 6 |
| `get_kc_client()` singleton via `lru_cache` | PASS | All 6 |
| Orchestrator tm_client: login removed, service token injected | PASS | T059 |
| Dispatcher reporter: service token injected | PASS | T060 |
| Dispatcher context_builder: token block in agent context | PASS | T061 |
| UIM tm_client: service token injected | PASS | T062 |
| Dispatcher `core/security.py` deleted | PASS | T063 |
| UIM migration: safe UUID→TEXT pattern | PASS | T064 |
| TM migration: safe UUID→TEXT pattern, 6 columns, 5 tables | PASS | T065 |
| `downgrade()` raises `NotImplementedError` (constitution §XXI) | PASS | Both migrations |
| All TM ORM models: TEXT user identity fields | PASS | T067 |
| UIM `PromptSession.user_id: Mapped[str]` | PASS | T066 |
| UIM `SessionService` uses `str` user_id | PASS | T068 |
| TM schemas use `str` user identity fields | PASS | T069 |

---

### Security Checklist

- [x] No service-to-service calls use locally-signed JWTs for identity (all use KeycloakServiceClient)
- [x] Client Credentials token is never logged or included in exception messages (C-KC-04)
- [x] Token refresh uses monotonic clock and 30s safety buffer (C-KC-01)
- [x] Concurrent token refresh is serialized by asyncio.Lock (C-KC-02)
- [x] Non-200 from Keycloak raises UpstreamError (C-KC-03)
- [x] Destructive migrations cannot be rolled back (constitution §XXI enforced)
- [x] User identity in DB is now Keycloak sub (opaque string), no FK to local users table

---

### Required Follow-Up

| ID | Action | Owner | Priority |
|----|--------|-------|----------|
| M7-01 | Consolidate `UpstreamError` import from `src.core.exceptions` in 4 services | backend | Minor |
| M7-02 | Add `test_keycloak_client.py` to context-distiller, agent-tools, ticket-manager | autotester | Minor |
