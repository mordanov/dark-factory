# Security Review: Planning Agent for Prompt Studio

**Feature**: `003-planning-agent`
**Reviewer**: Security Architect Agent
**Date**: 2026-06-23
**Spec version**: spec.md (Draft)
**Constitution version**: 1.2.0

---

## Executive Summary

The Planning Agent feature introduces three new trust boundaries and several high-value
attack surfaces: an LLM-mediated plan generation pipeline, a background ticket-creation
worker, cross-service HTTP calls (TM + ContextDistiller), and user-controlled inline
plan editing. The design as specified in spec.md / plan.md is architecturally sound for
a low-to-medium threat model. All critical constitution principles (XIII–XVI) are
respected by the design. This review identifies **seven security requirements** and
**two advisory findings** that implementors must address.

---

## 1. Trust Boundary Map

```
[Browser / User]
      │ Bearer JWT (per request)
      ▼
[Nginx reverse proxy]
      │
      ▼
[user-input-manager (UIM)]  ─── Bearer TM_SERVICE_JWT ──▶  [ticket-manager]
      │                      ─── Bearer CD_SERVICE_JWT ──▶  [context-distiller]
      │
      ▼
[PostgreSQL: df_user_input]   (prompt_plans + prompt_sessions)

[OpenAI API] ◀─── OPENAI_API_KEY (outbound, no user data in prompt except refined_prompt)
```

**Trust boundaries crossed by this feature**:
- B1: Browser → UIM (inbound, user-authenticated)
- B2: UIM → Ticket Manager (outbound, service-authenticated)
- B3: UIM → ContextDistiller (outbound, service-authenticated)
- B4: UIM → OpenAI (outbound, API-key authenticated)

---

## 2. STRIDE Threat Model

### 2.1 Spoofing

| ID | Threat | Control | Status |
|----|--------|---------|--------|
| S1 | Attacker forges Bearer JWT to access another user's plan | Session ownership check on all 5 new endpoints; `user_id` verified against `session.user_id` | ✅ Designed-in (verify in implementation) |
| S2 | Service-to-service impersonation (TM, CD calls) | `TM_SERVICE_JWT` / `CD_SERVICE_JWT` injected via env var | ✅ Designed-in |

### 2.2 Tampering

| ID | Threat | Control | Status |
|----|--------|---------|--------|
| T1 | User submits malicious `plan_content` on `PUT /plan` with schema-valid but adversarial title/description (XSS payload, SQL probe, prompt injection for downstream LLM reads) | `PlanValidator` enforces max-length and allowed literal fields. All display must HTML-escape. | ⚠️ **SR-001** — require HTML-safe validation; implementor must not render titles/descriptions as raw HTML |
| T2 | User modifies `depends_on` list to reference tasks in a different story (cross-story cycle) | `PlanValidator` enforces within-story referential integrity and DFS cycle detection | ✅ Designed-in |
| T3 | Plan `status` field spoofed via `PUT /plan` body | `PlanUpdateRequest` only accepts `plan_content`; status transitions are server-side | ✅ Designed-in |
| T4 | Race condition: two concurrent `POST /plan/confirm` calls bypass single-confirm gate | `update_status` must use optimistic locking or a DB-level guard (e.g. `WHERE status = 'ready'`) | ⚠️ **SR-002** — require atomic status transition in `PlanRepository.update_status` |

### 2.3 Repudiation

| ID | Threat | Control | Status |
|----|--------|---------|--------|
| R1 | User denies confirming a plan that created tickets | `prompt_plans.created_at`, `updated_at`, `status` history in DB; all state transitions server-side | ✅ Adequate for internal audit |
| R2 | No audit log of which user triggered generation / confirmation | Structured log with `user_id`, `session_id`, action should be emitted at each transition | ⚠️ **SR-003** (advisory) — emit `structlog` entries at generate, confirm, and tickets_created transitions |

### 2.4 Information Disclosure

| ID | Threat | Control | Status |
|----|--------|---------|--------|
| I1 | TM credentials / service JWTs leak into application logs | Plan docs state "TM credentials MUST NOT appear in logs"; must verify no `httpx` response body logging that includes auth headers | ✅ Constitution requirement — verify in implementation |
| I2 | `agent_config` content (project overrides) exposed to wrong user | `GET /plan` checks session ownership; `agent_config` is part of `PlanResponse` | ✅ Ownership check designed-in |
| I3 | `plan_content` from session A exposed to user B via shared plan_id lookup | Endpoints route via `session_id`, not `plan_id` directly; session ownership checked | ✅ Designed-in |
| I4 | OpenAI API receives sensitive user data beyond `refined_prompt` | LLM prompt must only include the validated `refined_prompt` text; no PII from user profile, no session metadata | ⚠️ **SR-004** — review `planning_llm.py` prompt construction; no extra context unless explicitly reviewed |
| I5 | LLM-generated `plan_content` / `agent_config` stored in plain JSONB; DB credentials leak exposes plans | PostgreSQL-level access control (service-specific DB user) handles this; no additional control needed at app level | ✅ Existing DB isolation |

### 2.5 Denial of Service

| ID | Threat | Control | Status |
|----|--------|---------|--------|
| D1 | Attacker triggers repeated `POST /plan` to exhaust LLM API quota | Endpoint requires `status == approved`; plan row created on first call; subsequent calls return 409 until regeneration is explicit | ✅ State machine limits to one active generation per session |
| D2 | Runaway background ticket creation job blocks other sessions | BackgroundTasks runs in the same event loop; a single long-running `_create_tickets` could degrade throughput under load | ⚠️ **SR-005** (advisory) — document known limitation; consider per-session timeout for `_create_tickets` (e.g. 120s total) |
| D3 | Malicious user submits plan with 10 stories × 10 tasks, maximizing TM API calls (101 requests) | Validator enforces 10/10 limit; all 101 calls still happen | ✅ Bounded by design; acceptable at human interaction rate |

### 2.6 Elevation of Privilege

| ID | Threat | Control | Status |
|----|--------|---------|--------|
| E1 | User attempts to confirm another user's plan by guessing `session_id` | `403` if session not owned by authenticated user; session UUIDs are non-guessable | ✅ Designed-in |
| E2 | Background task `_create_tickets` runs with service-level TM credentials; a compromised plan could trigger creation of arbitrary TM tickets | Plan content is validated before confirm; title/description max-length enforced; TM ticket type is constrained to `epic|story|task|implementation|investigation` | ✅ Adequate |
| E3 | `agent_config.agent_overrides` content could influence downstream agent behaviour via ContextDistiller; prompt injection via override_text | Override text is stored as opaque string; Orchestrator consumes it as a system prompt addition — injection risk is in how Orchestrator uses it, not in storage | ⚠️ **SR-006** — mark `override_text` fields as prompt-injection risk in ContextDistiller; recommend length cap (≤2000 chars) and output validation if used in agent prompts |

---

## 3. Security Requirements

These MUST be implemented and verified before the feature ships.

### SR-001 — HTML-Safe Plan Node Rendering (Blocker)

**Risk**: Stored XSS via `title` or `description` fields in plan nodes rendered in
`PlanningModal.tsx`.

**Requirement**: All plan node titles and descriptions rendered in the React component
MUST be treated as plain text (no `dangerouslySetInnerHTML`). The inline-edit
implementation MUST use controlled `<input>` / `<textarea>` elements, not `contentEditable`
without sanitization.

**Verification**: Code review of `PlanningModal.tsx` confirms no `dangerouslySetInnerHTML`
for plan node content. Penetration test: inject `<script>alert(1)</script>` as a story
title via `PUT /plan`; confirm it is rendered as escaped text, not executed.

---

### SR-002 — Atomic State Transition for Confirm (Blocker)

**Risk**: Two rapid concurrent `POST /plan/confirm` requests could both pass the
`status == "ready"` check and both launch `_create_tickets`, creating duplicate tickets.

**Requirement**: `PlanRepository.update_status` MUST use a conditional update:
```sql
UPDATE prompt_plans
SET status = 'confirmed', session_id = ...
WHERE id = :plan_id AND status = 'ready'
```
If zero rows are updated, raise a conflict error. Do not rely on application-level
check-then-set with a separate read.

**Verification**: Integration test: send two concurrent `POST /plan/confirm` requests
for the same session; verify only one returns 202 and the other returns 409.

---

### SR-003 — Structured Audit Logging at State Transitions (Required)

**Risk**: Without audit trail, it is impossible to investigate disputes about when
a plan was confirmed or who triggered ticket creation.

**Requirement**: Using `structlog`, emit a structured log event at each of:
- `POST /plan` triggered (include `user_id`, `session_id`, timestamp)
- Plan generation succeeded / failed
- `POST /plan/confirm` called (include `user_id`, `session_id`)
- All tickets created successfully (include `session_id`, `tm_epic_id`, ticket count)
- Partial failure (include `session_id`, `created_count`, `total`)

Log format MUST NOT include `plan_content` (PII / sensitive project data) or any credential.

**Verification**: Check logs after a full end-to-end test flow; confirm events present
without credential or plan body leakage.

---

### SR-004 — LLM Prompt Minimisation (Required)

**Risk**: `planning_llm.py` could inadvertently include session metadata, user profile
data, or database identifiers in the LLM prompt, leaking data to OpenAI.

**Requirement**: The prompt sent to OpenAI for `generate_plan` MUST include only the
`refined_prompt` text (the user's approved prompt content). It MUST NOT include:
- `session_id`, `user_id`, `tm_project_id`, or any internal identifier
- Any environment variable value
- Any other session field

The prompt for `generate_agent_config` MAY include the plan content (Epic/Story titles)
and tech stack context but MUST NOT include TM ticket IDs, service credentials, or
internal URLs.

**Verification**: Code review of `planning_llm.py`; log the prompt shape (not content)
in debug mode and confirm no identifiers present.

---

### SR-005 — Background Task Timeout (Advisory / Strongly Recommended)

**Risk**: A `_create_tickets` run that encounters a hung TM connection could block the
event loop indefinitely, degrading the service for other users.

**Requirement**: Wrap the `_create_tickets` background task body in an `asyncio.timeout`
(Python 3.11+ stdlib) of 120 seconds. On timeout, set plan status to `error` with
`validation_errors = ["Ticket creation timed out — please retry"]`.

**Verification**: Unit test mocking TM to hang indefinitely; verify task terminates
within timeout and plan enters `error` state.

---

### SR-006 — Agent Override Prompt Injection Boundary (Advisory)

**Risk**: `agent_config.agent_overrides[].override_text` is LLM-generated content that
will later be consumed as a system prompt fragment by Dark Factory agents. An adversarially-
crafted prompt could cause the LLM to produce override text containing prompt injection
payloads (e.g., "Ignore previous instructions...").

**Requirement**: 
1. Cap `override_text` at 2000 characters (add `max_length=2000` to `AgentOverride` schema).
2. When ContextDistiller stores agent config, log a `warn` if any `override_text` contains
   common injection markers (`ignore previous`, `system:`, `<|`).
3. Document in `AgentOverride` schema that this field is security-sensitive and must not
   be rendered unsanitized in agent system prompts.

**Verification**: Schema review confirms `max_length=2000`; store a test config with a
known injection string and verify the warn log fires.

---

### SR-007 — `CONTEXT_DISTILLER_TIMEOUT_SECONDS` Config Default (Required)

**Risk**: If `CONTEXT_DISTILLER_TIMEOUT_SECONDS` is not set, the `httpx.AsyncClient`
call may use `httpx` default (5s) or none. The spec says 10s — an explicit enforced
default prevents misconfiguration.

**Requirement**: `config.py` MUST set `CONTEXT_DISTILLER_TIMEOUT_SECONDS: int = 10`
with a `ge=1, le=60` validator. `_store_agent_config` MUST use this value explicitly
in `httpx.AsyncClient(timeout=settings.CONTEXT_DISTILLER_TIMEOUT_SECONDS)`.

**Verification**: Test that starting the service without the env var uses 10s; test that
a ContextDistiller mock that hangs past 10s causes `_store_agent_config` to log and return
rather than block forever.

---

## 4. Authentication & Authorization Summary

All five new endpoints follow the existing `auth_adapter.py` + `UserDep` pattern:

| Endpoint | Auth | Ownership check |
|----------|------|-----------------|
| `POST /sessions/{id}/plan` | Bearer JWT via `UserDep` | `session.user_id == current_user.id` |
| `GET /sessions/{id}/plan` | Bearer JWT via `UserDep` | `session.user_id == current_user.id` |
| `PUT /sessions/{id}/plan` | Bearer JWT via `UserDep` | `session.user_id == current_user.id` |
| `POST /sessions/{id}/plan/confirm` | Bearer JWT via `UserDep` | `session.user_id == current_user.id` |
| `GET /sessions/{id}/plan/status` | Bearer JWT via `UserDep` | `session.user_id == current_user.id` |

**AUTH_MODE=local** MUST remain unchanged (no new logic added). `AUTH_MODE=keycloak`
MUST raise `NotImplementedError`. These are unchanged from the existing adapter.

---

## 5. Secrets Management

| Secret | Location | Committed to Git? |
|--------|----------|-------------------|
| `OPENAI_API_KEY` | `infra/.env` | NO — gitignored |
| `TM_SERVICE_JWT` (or equivalent) | `infra/.env` | NO — gitignored |
| `CD_SERVICE_JWT` (or equivalent) | `infra/.env` | NO — gitignored |
| `PLANNING_MODEL` | `infra/.env.example` (placeholder) | YES (placeholder only) |
| `CONTEXT_DISTILLER_BASE_URL` | `infra/.env.example` (non-secret URL) | YES |

**T038 must add** `PLANNING_MODEL`, `CONTEXT_DISTILLER_BASE_URL`, `CONTEXT_DISTILLER_TIMEOUT_SECONDS`
to `infra/.env.example` with placeholder values and comments. Confirm no credential appears.

---

## 6. Token Storage (Zustand — Frontend)

The planning feature adds `planStore.ts`. Constitution requirement: access tokens MUST
reside in Zustand in-memory state only — never `localStorage`, `sessionStorage`, or `cookie`.

**SR-FRONTEND-01**: `planStore.ts` MUST NOT read or write `localStorage`/`sessionStorage`
for any field. The `plan`, `planStatus`, `agentConfig`, `creationProgress` state fields
are plan data, not credentials — they may be lost on page reload (the API refetches from
the backend). Access tokens remain in the existing `authStore` (in-memory Zustand); no
change is needed.

**Verification**: Code review of `planStore.ts`; confirm no `localStorage.*` / `sessionStorage.*`
references.

---

## 7. Data Retention and Privacy

`plan_content` and `agent_config` are stored as JSONB in PostgreSQL. They contain:
- User-authored Epic/Story/Task titles and descriptions (user-generated content)
- LLM-generated project analysis in `agent_config`

These fields MUST be included in any future data deletion / right-to-erasure flow
(not in scope for v1, but flagged for future compliance). `ON DELETE CASCADE` on
`prompt_plans.session_id` ensures plans are deleted when sessions are deleted.

---

## 8. Security Acceptance Criteria

The following tests MUST pass before the feature is merged:

| ID | Test | Expected |
|----|------|----------|
| SAC-001 | `PUT /plan` with `<script>alert(1)</script>` as title | Stored as escaped text; rendered without script execution in browser |
| SAC-002 | Two concurrent `POST /plan/confirm` on same session | Exactly one 202; other returns 409 |
| SAC-003 | `GET /sessions/{id}/plan` with a session owned by user B while authenticated as user A | 403 Forbidden |
| SAC-004 | Log inspection after plan generation flow | No `OPENAI_API_KEY`, no TM JWT, no `plan_content` body in log lines |
| SAC-005 | Start service without `CONTEXT_DISTILLER_TIMEOUT_SECONDS` set | Defaults to 10s; ContextDistiller mock that hangs 11s causes log warn + return |
| SAC-006 | `planStore.ts` static analysis | Zero references to `localStorage` or `sessionStorage` |
| SAC-007 | `POST /plan` on session with `status == plan_ready` (already generating or generated) | 409 Conflict |

---

## 9. Residual Risks

| Risk | Likelihood | Impact | Accepted By | Notes |
|------|-----------|--------|-------------|-------|
| LLM generates plan content that is offensive or misleading | Medium | Low | Product (user confirms before tickets created) | Confirmation gate (XIV) is the primary mitigation |
| OpenAI API key compromise allows billing abuse | Low | Medium | Ops | Rotate key immediately on incident; usage alerts recommended |
| Background ticket creation leaves partial state under load | Low | Medium | Architecture (retry designed-in) | SR-005 timeout mitigates long hangs |
| `agent_config` injection via LLM output | Low | Medium | Pending SR-006 | Cap + log ward; deeper sandboxing deferred |

---

*Security review complete. All blockers (SR-001, SR-002) must be resolved before merge.
SR-003, SR-004, SR-005, SR-006, SR-007 are required or strongly recommended.*
