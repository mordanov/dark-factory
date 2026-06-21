# Research: Orchestrator Integration Extensions

**Branch**: `005-orchestrator-extensions` | **Date**: 2026-06-21

---

## 1. Service Account Authorization

**Decision**: Identify the Dark Factory service account by matching the authenticated user's email against the `TICKET_MANAGER_SERVICE_EMAIL` environment variable. No new role is introduced.

**Rationale**: The constitution mandates exactly two roles (`administrator` and `user`). A third role would require a MAJOR amendment. Instead, the service account is provisioned as a regular user account (role: `user`) whose email is pre-configured in `.env`. A new FastAPI dependency `require_service_account` checks `current_user.email == settings.ticket_manager_service_email`. This integrates cleanly with the existing `require_role` pattern in `src/core/security.py`.

For the FSM PATCH endpoint, access is granted to the service account OR an administrator (admins need to be able to update FSM fields for debugging). Override endpoint remains admin-only via the existing `require_role("administrator")` dependency.

**Alternatives considered**:
- New `service` role — rejected, requires constitution MAJOR amendment.
- API key / separate auth scheme — rejected, would require parallel auth middleware, inconsistent with existing Bearer token pattern.

---

## 2. Cursor-Based Pagination for `/orchestrator/pending`

**Decision**: Use a composite opaque cursor encoding `(updated_at, id)` as a base64-encoded JSON string. The query filters `(updated_at, id) > (cursor_updated_at, cursor_id)` using keyset pagination.

**Rationale**: The pending endpoint is a high-frequency polling endpoint where offset pagination would cause missed or duplicate tickets under concurrent writes (new tickets added between pages shift offsets). Keyset pagination using `(updated_at, id)` is stable and efficient with the existing `idx_tickets_updated_at`-style index. The cursor is opaque to callers, encoded in base64 to discourage manual construction.

**Index required**: Add a composite index on `(updated_at, id)` to the `tickets` table to support efficient keyset pagination.

**Alternatives considered**:
- Offset pagination — rejected, produces duplicates/gaps under concurrent writes.
- Pure `id`-based cursor — rejected, doesn't naturally sort by recency which is the primary ordering need for polling.

---

## 3. Orchestrator Audit Log vs. Existing Ticket Events

**Decision**: Create a new `orchestrator_audit_events` table. Do NOT reuse or extend `ticket_events`.

**Rationale**: The existing `ticket_events` model requires `actor_id` (a FK to `users`) and `actor_role` (the `UserRole` enum), and uses JSONB blobs for `prev_state`/`new_state`. The orchestrator audit log has a different schema: `event` (string type like `ADVANCE|BLOCK`), `actor` (string identifier like `"orchestrator"`), `from_state`/`to_state` (FSM status strings), and `details` (free-text string). Mixing these into `ticket_events` would require nullable columns on both tables or a polymorphic design that adds complexity. A clean separate table with a fixed schema is simpler and more readable.

**Constitution Principle II note**: The constitution specifies actor identity as "user ID and role." The orchestrator is a service agent, not a human user — there is no meaningful `user_id`. The `actor` field stores the service identifier string instead. This is a justified deviation documented here: the orchestrator service is the system actor; its identity is the service account email or the literal string `"orchestrator"`. This deviation does NOT bypass audit requirements — every orchestrator action is still immutably recorded.

**Alternatives considered**:
- Extend `ticket_events` with nullable orchestrator-specific columns — rejected, pollutes the existing event schema and violates single-responsibility.
- Reuse `ticket_events` with a different event_type prefix — rejected, `actor_id` FK constraint forces a user record to exist for every event type.

---

## 4. Tag Delta Endpoint

**Decision**: Add a new `POST /api/v1/projects/{project_id}/tickets/{ticket_id}/tags/delta` endpoint accepting `{"add": [...], "remove": [...]}`. Keep the existing `POST /add-tag` and `DELETE /remove-tag` endpoints unchanged.

**Rationale**: The existing `POST /{ticket_id}/tags` endpoint in `src/api/v1/tickets.py` accepts `{"name": "..."}` (single-add) and is used by the frontend. Changing its contract would be a breaking change. A new delta endpoint at a distinct path provides the atomic add/remove needed by the orchestrator without breaking existing callers.

The delta operation is atomic: both adds and removes are applied in a single database transaction. Adding an already-present tag and removing an absent tag are both silently idempotent.

**Alternatives considered**:
- Replace existing tag endpoint — rejected, breaking change to frontend consumers.
- Separate `POST /add` and `DELETE /remove` calls — rejected, not atomic; race conditions possible when orchestrator needs to simultaneously add and remove tags.

---

## 5. FSM Status Enum: Separate vs. Extending TM Status

**Decision**: `fsm_status` is a new PostgreSQL enum type (`fsm_status_enum`) independent of the existing `ticket_status` enum. It is nullable (NULL = not yet assigned by orchestrator).

**Rationale**: The TM `TicketStatus` (`OPEN/IN_PROGRESS/IN_REVIEW/DONE/CLOSED`) is the human-facing workflow. `FsmStatus` (`backlog/triage/.../done/BLOCKED`) is the orchestrator's pipeline state. They evolve independently. Keeping them separate preserves Principle V (controlled workflow evolution) for both.

Default value for existing tickets: NULL (not `backlog`). The orchestrator treats NULL the same as `backlog` during polling. This avoids a non-nullable default that would silently put every existing ticket into the orchestrator's queue.

**Alternatives considered**:
- Extend `TicketStatus` with FSM values — rejected, mixes human and machine workflows, violates Principle V.
- Use a string column instead of enum — rejected, loses database-level validation; inconsistent with project patterns.

---

## 6. Migration Strategy

**Decision**: Two migrations:
- **015**: Add FSM columns to `tickets` table + composite index for polling. Add `override` (boolean) and `override_reason` (text) to the FSM column set.
- **016**: Create `orchestrator_audit_events` table.

Both migrations are backward-compatible: all new columns are nullable or have server defaults. Rollback paths remove the added columns/table. The `fsm_status_enum` PostgreSQL type is created in migration 015 and dropped in its rollback.

**Override field note**: `override` (boolean, default `false`, not null) and `override_reason` (text, nullable) are stored on the `tickets` table as FSM fields — the orchestrator reads and clears them via the FSM PATCH endpoint.

---

## 7. `include_fsm` Query Parameter

**Decision**: Add `include_fsm: bool = Query(default=False)` to the existing `GET /api/v1/projects/{project_id}/tickets` endpoint. When `True`, the response uses a new `TicketWithFsmResponse` schema that extends `TicketResponse` with FSM fields. When `False`, the existing `TicketResponse` is returned unchanged.

**Rationale**: The existing `list_tickets` in `src/services/ticket_service.py` already eagerly loads the ticket. Adding optional FSM fields to the response is a non-breaking additive change.

---

## 8. Batch FSM Status Endpoint Path

**Decision**: Route as `POST /api/v1/tickets/batch-fsm-status` (under the existing `/tickets` router prefix in `src/api/v1/tickets.py`).

**Rationale**: The spec defines the path as `/api/tickets/fsm-status-batch` (no `/v1/`). All existing endpoints use `/api/v1/`. We align with the existing prefix convention. The method is POST (not GET) because the request body contains an array of IDs — FastAPI and HTTP standards support this pattern for batch lookups.

**Note for orchestrator integration**: The orchestrator must use `/api/v1/tickets/batch-fsm-status` rather than the path in the spec document.

---

## 9. Frontend Impact

**Decision**: No frontend changes required for this feature. All new endpoints are service-to-service (orchestrator ↔ TM). The existing React frontend is unaffected. FSM fields may appear in API responses but the frontend ignores unknown fields.

**Rationale**: The React frontend uses only documented, versioned endpoints per Principle VI. The new endpoints are not consumed by the frontend in this feature scope.
