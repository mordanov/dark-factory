# Research: Agent Maturity Platform

**Branch**: `003-agent-maturity` | **Phase**: 0

---

## Decision 1: Capability Registry Runtime Storage Layer

**Decision**: New PostgreSQL tables in `agent-dispatcher`'s existing `df_dispatcher` database.

**Rationale**: The dispatcher already owns `AgentRun` and `BrainstormSession` tables in `df_dispatcher`. Adding `AgentWorkerRecord` and `AgentLifecycleEvent` tables here keeps all agent execution state in one transactional boundary, avoids cross-service DB access (constitution constraint), and requires no new service. The `CapabilityRegistry` class already exists at `src/services/capability_registry.py` and loads from YAML at startup — this layer handles static declarations. A new `AgentWorkerRepository` handles the mutable runtime layer.

**Alternatives considered**:
- **Standalone service**: More operationally isolated but adds a new failure dependency in the hot path and violates "no new service for phase 1" assumption.
- **In-memory only**: Lost on restart; no heartbeat history for audit; fails FR-012 (immutable audit log).

---

## Decision 2: Inter-Agent Consultation Transport

**Decision**: Synchronous HTTP request-response, entirely mediated by `agent-dispatcher`.

**Rationale**: Stays within existing HTTP service boundary model. `agent-dispatcher` exposes a new `POST /api/v1/consult` endpoint. The requesting agent posts a `ConsultationRequest`; `agent-dispatcher` identifies the best available peer via the registry, calls the peer's in-process agent runner with the question payload, and returns the `ConsultationResponse` in the same HTTP response. The 60-second SLA (SC-004) is enforced as a server-side `asyncio.wait_for` timeout on the forwarded call. No message bus, polling infrastructure, or callback URLs required.

**Alternatives considered**:
- **Async polling**: Adds a `ConsultationRequest` table, polling loop, and roundtrip latency overhead. Necessary only if consultation responses take > 60s — not the case for targeted domain questions.
- **Webhook/callback**: Requires agents to expose an HTTP server, which is incompatible with the current `claude_code` runner model (subprocess).

---

## Decision 3: Persistent Worker Runtime Shape

**Decision**: Logical persistence only — a `AgentWorkerRecord` DB row per running agent process instance; underlying execution remains process-per-ticket.

**Rationale**: The current `claude_code` runner spawns a subprocess per ticket. Changing this to long-running processes would require a full runner rewrite and process supervision. Logical records give all the value (availability signaling, heartbeats, liveness detection, audit trail) at zero disruption to the existing execution model. Agents POST a `/register` call on startup and send periodic `/heartbeat` POSTs; the `DispatchWorker` checks status in `AgentWorkerRecord` before issuing a run. Crash detection uses a background liveness sweep task in `agent-dispatcher`.

**Alternatives considered**:
- **Long-running worker process**: Better for throughput but requires process management, port allocation per agent, and health probe infrastructure. Deferred to a future maturity phase.
- **Containerized sidecar**: Same issue — requires Docker lifecycle hooks and reimplementation of the runner. Out of scope for phase 1.

---

## Decision 4: Shared Working Memory Service Ownership

**Decision**: `agent-dispatcher` owns shared working memory in `df_dispatcher` (new `WorkingMemoryEntry` table). Orchestrator reads it via `GET /api/v1/working-memory/{ticket_id}`.

**Rationale**: The hot path for working memory (append during active execution, read at gate time) stays entirely within the `agent-dispatcher` service boundary. No cross-service write during execution. `context-distiller` continues to own distilled project memory post-completion; a distillation trigger can optionally promote working memory entries on ticket closure (same pattern as today's post-run distillation). Retention is 30 days via a periodic cleanup job in `agent-dispatcher`.

**Alternatives considered**:
- **`context-distiller` ownership**: Every write during execution crosses a service boundary under load and adds a latency/availability dependency on `context-distiller` in the hot path.
- **Split (active/historical)**: Adds operational complexity (two read paths, promotion job). Deferred unless working memory volume exceeds `df_dispatcher` capacity.

---

## Decision 5: Assignment Resolution Ownership

**Decision**: Orchestrator specifies `required_capabilities` in the job trigger payload; `agent-dispatcher` is the sole resolver via the registry; matched record returned to Orchestrator in the result payload.

**Rationale**: Preserves Orchestrator FSM sovereignty — it continues to decide *what* is needed (via `to_state` + ticket tags → derived required capabilities). Dispatcher decides *who* by querying the live registry including availability status — information the Orchestrator does not (and should not) hold. The matched `AgentCapabilityRecord` is returned with the run result so the Orchestrator LLM has full context on the next cycle. Fallback to static role-based assignment (current behavior) is triggered when the registry returns no match or is unavailable.

**Alternatives considered**:
- **Orchestrator reads registry directly**: Requires Orchestrator to call `agent-dispatcher`'s API before assigning — adding a synchronous dependency in the Orchestrator's hot path. Rejected to preserve existing job-trigger flow.
- **Dispatcher resolves autonomously without hints**: Orchestrator loses visibility into what capability was required; assignment becomes a black box. Rejected for auditability (FR-032).

---

## Existing Code: What's Already There (Reuse)

| Component | Location | Status | Reuse plan |
|---|---|---|---|
| `CapabilityRegistry` YAML loader | `src/services/capability_registry.py` | Complete | Extend with `confidence` field in `AgentCapability`; `get_by_capability(skill, min_confidence)` method |
| `AgentCapability` dataclass | `capability_registry.py` | Complete | Add `confidence: dict[str, int]` field |
| `AgentRun` ORM model | `src/models/models.py` | Complete | No changes; `WorkingMemoryEntry` and `AgentWorkerRecord` are new tables |
| `CapabilityRegistry.to_yaml_string()` | `capability_registry.py` | Complete | Already included in reporter payload |
| `reporter.py` registry payload | `src/services/reporter.py` | Complete | Add `required_capabilities` + matched record to result payload |
| `dispatcher_service.py` | `src/services/dispatcher_service.py` | Complete | Add capability-check before `_resolve_prompt_path` |
| Alembic setup | `alembic/` | Complete | Add new migration for 3 new tables |
| `KeycloakValidator` auth | `src/core/auth_adapter.py` | Complete | Reuse for new endpoints; consultation endpoint requires service token |

---

## New API Endpoints Needed in `agent-dispatcher`

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/workers/register` | POST | Agent registers logical worker record on startup |
| `/api/v1/workers/{role_id}/heartbeat` | POST | Periodic liveness signal |
| `/api/v1/workers/{role_id}/drain` | POST | Graceful shutdown signal |
| `/api/v1/workers` | GET | Registry dashboard — all workers with status |
| `/api/v1/consult` | POST | Synchronous peer consultation request |
| `/api/v1/working-memory/{ticket_id}` | GET | Read all entries for a ticket |
| `/api/v1/working-memory/{ticket_id}` | POST | Append a new entry |

---

## Registry YAML Extension (Backward-Compatible)

The existing `registry.yaml` schema needs two additions:
1. `confidence` per-skill map (optional; default: `{}` — all skills equal confidence)
2. No removals from the existing schema — purely additive

```yaml
# New per-agent optional field (existing agents get default empty dict)
capabilities:
  - python_backend    # existing: no confidence specified → treated as max
confidence:           # NEW optional field
  python_backend: 90
  fastapi: 85
```

This is backward-compatible: agents without a `confidence` field behave as before.

---

## Constitution Check: Phase 0

| Principle | Status | Notes |
|---|---|---|
| Registry is single source of truth for agent metadata | ✅ PASS | YAML remains source for static declarations; DB extends with runtime state only |
| No hardcoded role IDs outside registry | ✅ PASS | New code references `role_id` values loaded from registry |
| LLM selects, registry constrains | ✅ PASS | Required capabilities are passed to Orchestrator LLM context via result payload |
| Credentials written by Dispatcher before spawn | ✅ PASS | Unchanged; `_write_credentials` stays in `dispatcher_service.py` |
| Registry loaded once at startup | ✅ PASS | YAML still loaded at startup; DB state queried per-request (bounded query) |
| No cross-service DB access | ✅ PASS | All new tables in `df_dispatcher`; Orchestrator reads via HTTP API |
| Service boundaries over HTTP | ✅ PASS | All new cross-service communication via HTTP endpoints |
| FSM sovereignty in Orchestrator | ✅ PASS | Dispatcher never mutates FSM state; Orchestrator specifies required capabilities |
