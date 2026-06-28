# Feature Specification: Agent Maturity Platform

**Feature Branch**: `003-agent-maturity`  
**Created**: 2026-06-28  
**Status**: Draft  

## Problem Statement

Dark Factory currently orchestrates work by assigning tickets to agents based on static role definitions and LLM reasoning. Three significant gaps limit the platform's ability to scale autonomous multi-agent execution:

1. **Limited inter-agent communication depth**: agents collaborate only through a coordinator-mediated brainstorm loop; they cannot request help from peers mid-task or share artifacts in real-time.
2. **Unregistered agent runtime model**: agents are spawned as short-lived processes per ticket with no lifecycle registration, availability signaling, or failure recovery between runs. There is no persistent record of which agent instances are active or healthy.
3. **Static capability discovery**: the Orchestrator selects agents based on hard-coded role definitions rather than a live, queryable index of what each agent can do, how confident it is, and whether it is currently available.

These gaps mean the platform cannot take full advantage of specialization across the agent pool, wastes resources on blind assignment failures, and cannot gracefully adapt when an agent is unavailable or overwhelmed.

## Business Value

Closing these gaps delivers:
- Higher task completion rates through better-matched assignments and peer consultation.
- Reduced wasted runs from capability mismatches or unavailable agents.
- Auditable, deterministic assignment decisions that operators can inspect and tune.
- A foundation for auto-scaling the agent pool as project load increases.

---

## User Scenarios & Testing

### User Story 1 — Capability-Based Assignment (Priority: P1)

As a platform operator, I want the Orchestrator to select agents based on a live capability registry — not just static role names — so that tickets are assigned to agents whose declared skills, availability, and confidence best match the work.

**Why this priority**: Mis-assignment is the most frequent source of failed runs today. Getting the right agent for the right ticket is the highest-leverage improvement.

**Independent Test**: Can be fully tested by sending a ticket through the orchestration loop and verifying that the assigned agent's capability record matches the ticket's requirements, with the decision logged in the audit trail.

**Acceptance Scenarios**:

1. **Given** a ticket requiring `python_backend` skill, **When** the Orchestrator evaluates candidates, **Then** only agents with `python_backend` in their declared capabilities and `available` status are considered, and the selected agent is recorded in the audit entry.
2. **Given** no agent with the required capability is currently available, **When** the Orchestrator evaluates, **Then** the ticket is placed in `WAIT` state with a blocked reason that names the missing capability — never assigned to an incompatible agent.
3. **Given** an agent reports its confidence for a skill as below the configured threshold, **When** the Orchestrator evaluates, **Then** that agent is ranked lower (or excluded) and the decision rationale includes the confidence shortfall.
4. **Given** the capability registry is unavailable, **When** the Orchestrator evaluates, **Then** it falls back to current static role-based assignment and logs a degraded-mode audit entry.

---

### User Story 2 — Agent Availability and Lifecycle Registration (Priority: P2)

As a platform operator, I want agents to register their availability, heartbeat while active, and signal graceful shutdown, so that the Dispatcher never assigns work to an agent that is already at capacity or mid-shutdown.

**Why this priority**: Without lifecycle signals, the Dispatcher must blind-retry on failures. Lifecycle visibility eliminates unnecessary retries and reduces time-to-reassignment when an agent fails.

**Independent Test**: Can be fully tested by starting and stopping an agent worker process and observing that the registry status transitions from `offline` → `available` → `draining` → `offline`, with no new assignments issued during `draining` or `offline` states.

**Acceptance Scenarios**:

1. **Given** an agent worker starts up, **When** it completes initialization, **Then** it registers itself in the capability registry with status `available` and a current heartbeat timestamp.
2. **Given** a registered agent stops sending heartbeats for longer than the configured timeout, **When** the registry checks liveness, **Then** the agent's status is automatically set to `unhealthy` and no new tickets are assigned to it.
3. **Given** an operator signals a graceful shutdown, **When** the agent worker receives the signal, **Then** it transitions to `draining`, completes any in-progress run, then transitions to `offline`.
4. **Given** an agent worker crashes without signaling, **When** the liveness check runs, **Then** in-progress runs assigned to that agent are marked `timed_out`, and the Dispatcher triggers reassignment.

---

### User Story 3 — Peer Consultation During Task Execution (Priority: P3)

As an agent executing a complex ticket, I want to request structured input from a peer specialist mid-task — without interrupting the primary execution flow — so that I can resolve domain-specific questions without escalating the entire ticket to human review.

**Why this priority**: Peer consultation is valuable but optional for the first maturity phase. The capability registry (P1) and lifecycle model (P2) must be in place before peer routing is meaningful.

**Independent Test**: Can be fully tested by triggering a mock consultation request from one agent to another, verifying that the request is routed to a capable and available peer, and that the response is delivered back within the timeout window.

**Acceptance Scenarios**:

1. **Given** an executing agent needs domain input, **When** it submits a consultation request with a required capability, **Then** the platform identifies an available peer with that capability, forwards the request, and returns the peer's response to the originating agent within 60 seconds.
2. **Given** no peer is available with the required capability, **When** the consultation request is submitted, **Then** the originating agent receives a structured "no peer available" response and can continue independently or flag the question for human review.
3. **Given** a peer accepts a consultation request, **When** it responds, **Then** the exchange is appended to the shared working memory for the ticket, making it visible to all agents and to the Orchestrator at gate evaluation.
4. **Given** a consultation peer fails mid-response, **When** the timeout expires, **Then** the originating agent receives a timeout response and the failed peer's status is set to `unhealthy`.

---

### User Story 4 — Shared Working Memory for Active Tickets (Priority: P4)

As a platform operator, I want all agents working on or reviewing a ticket to read and append to a shared working memory space, so that no agent duplicates work already done by a peer and the Orchestrator can evaluate the full collaborative record at gate time.

**Why this priority**: Depends on peer consultation (P3) to be maximally useful; shared memory without consultation still provides value for brainstorm and multi-agent review flows.

**Independent Test**: Can be fully tested by having two agents independently read and write to a ticket's shared memory space and verifying that each can see the other's contributions without overwriting them.

**Acceptance Scenarios**:

1. **Given** two agents are assigned to the same ticket in a brainstorm round, **When** each appends a finding to shared working memory, **Then** both findings are visible to the other agent on the next read and to the Orchestrator in the gate evaluation payload.
2. **Given** shared working memory contains entries from multiple agents, **When** the Orchestrator evaluates a gate, **Then** the memory contents are included in the evaluation context, structured by author and timestamp.
3. **Given** an agent writes to shared working memory and a concurrent writer appends at the same time, **When** both writes complete, **Then** no entry is lost and both are durably stored with their respective author identities.

---

### Edge Cases

- What happens when a capability registry record for an agent is stale (not updated in > 5 minutes)?
- How does the system handle a ticket type that no registered agent declares capability for?
- What happens when an agent registers a capability version that the Orchestrator's matching logic does not recognize?
- How does the system behave during a full registry restart with agents already mid-run?
- What happens when a peer consultation response exceeds the maximum payload size?
- How does shared working memory handle a ticket that is reassigned mid-execution?

---

## Requirements

### Functional Requirements

#### A. Capability Registry

- **FR-001**: The system MUST maintain a queryable registry of agent capabilities. Static capability declarations (role identifier, skill set, technology affinities, confidence levels per skill) are sourced from the existing YAML definition files. Runtime state (availability status, heartbeat timestamps) is persisted in the `agent-dispatcher` service's own database, with no cross-service database access.
- **FR-002**: The registry MUST support versioned capability declarations so that an agent running a newer skill set does not break existing Orchestrator routing logic.
- **FR-003**: The Orchestrator MUST query the registry during assignment decisions and include the matched capability record in the audit entry.
- **FR-004**: The registry MUST expose a read endpoint that returns a filtered list of agents matching a required skill and minimum confidence threshold.
- **FR-005**: When no agent matches the required capability, the registry MUST return an explicit empty result rather than a partial or degraded match, so the Orchestrator can produce a deterministic WAIT decision.
- **FR-006**: Capability declarations MUST be backward-compatible: adding a new skill to an agent's record MUST NOT invalidate existing assignments or routing rules.

#### B. Agent Lifecycle and Availability

- **FR-007**: Each agent process MUST register a logical worker record in `agent-dispatcher` on startup, providing its role ID, declared capabilities, and initial status. The underlying execution model remains process-per-ticket; registration creates a durable logical identity in `df_dispatcher`, not a long-running process handle.
- **FR-008**: Registered agent processes MUST send liveness heartbeats at a configurable interval (default: 30 seconds) via HTTP to `agent-dispatcher`. Absence of a heartbeat for more than three consecutive intervals MUST trigger automatic status transition to `unhealthy` in the logical worker record.
- **FR-009**: The Dispatcher MUST check the logical worker record's current status before issuing a run. Workers with status `unhealthy`, `draining`, or `offline` MUST NOT receive new assignments.
- **FR-010**: Agent processes MUST be able to initiate a graceful drain by updating their logical worker record status to `draining`; the Dispatcher will complete the current in-progress run and then transition the record to `offline`.
- **FR-011**: When a crash is detected via missed heartbeats, any in-progress run owned by that logical worker record MUST be marked as `timed_out` and eligible for reassignment.
- **FR-012**: All status transitions (registration, heartbeat updates, drain, offline, unhealthy recovery) MUST be recorded in an immutable audit log.

#### C. Assignment Decision Contract

- **FR-013**: The Orchestrator MUST include a required capabilities specification (derived from ticket type, FSM state, and tags) in the job payload it sends to the Dispatcher. The Orchestrator MUST NOT call the capability registry directly; it specifies *what* is needed and delegates *who* to the Dispatcher.
- **FR-014**: The Dispatcher is the sole resolver of capability-based assignment. It MUST query its own capability registry, select the best-matched available agent, execute the assignment, and return the selected agent ID together with the full matching capability record to the Orchestrator in the result payload for audit. The Orchestrator uses this record to inform its LLM context on the next evaluation cycle.
- **FR-015**: The Orchestrator MUST remain the sole authority on FSM state transitions; the Dispatcher and registry MUST NOT mutate ticket FSM state directly.
- **FR-016**: When the Dispatcher falls back to static role-based assignment (registry unavailable), it MUST log a `degraded_assignment` audit event with the reason.

#### D. Inter-Agent Consultation

- **FR-017**: An executing agent MUST be able to submit a consultation request to `agent-dispatcher` via a single synchronous HTTP POST, identifying: the required capability, the question payload, the originating ticket ID, and a maximum wait time.
- **FR-018**: Upon receiving a consultation request, `agent-dispatcher` MUST identify an available peer with the required capability and forward the request to that peer via a synchronous HTTP call, returning the peer's response to the originating agent in the same HTTP response. If no peer is available, a structured "no peer available" response MUST be returned within 5 seconds without forwarding.
- **FR-019**: Consultation exchanges MUST be appended to the ticket's shared working memory with author identity, timestamp, and request/response payloads.
- **FR-020**: A single consultation request MUST NOT block the Orchestrator polling loop; consultation is an agent-initiated operation that runs entirely within the agent's own execution context, not on the Orchestrator's job worker.
- **FR-021**: Consultation responses MUST be scoped to the originating ticket; `agent-dispatcher` MUST reject any consultation request that does not include a valid ticket ID, and MUST NOT route responses across ticket boundaries.

#### E. Shared Working Memory

- **FR-022**: Each active ticket MUST have a scoped working memory space owned by `agent-dispatcher` and persisted in `df_dispatcher`, lasting for the duration of the ticket's active execution phase.
- **FR-023**: Any agent assigned to a ticket MUST be able to read all entries in that ticket's working memory via `agent-dispatcher`'s HTTP API, regardless of which agent authored them.
- **FR-024**: Appending to working memory MUST be an atomic, append-only operation via `agent-dispatcher`'s HTTP API; no agent may overwrite or delete another agent's entries.
- **FR-025**: The Orchestrator MUST retrieve the full working memory contents for a ticket via `agent-dispatcher`'s HTTP API and include them (structured by author and timestamp) in the gate evaluation context when the ticket reaches a review gate.
- **FR-026**: Working memory entries MUST be retained in `df_dispatcher` for at least 30 days after ticket closure for audit and retrospective review.

#### F. Security and Authorization

- **FR-027**: All inter-agent communication (consultation requests, working memory reads/writes) MUST be authenticated using service-scoped tokens issued by the platform identity provider.
- **FR-028**: An agent MUST only be permitted to write to working memory for tickets it is currently assigned to or participating in; cross-ticket writes MUST be rejected with an authorization error.
- **FR-029**: Consultation request payloads MUST be sanitized to prevent prompt-injection attacks before being forwarded to the peer agent.
- **FR-030**: All inter-agent messages, capability registry mutations, and working memory writes MUST be logged to an immutable audit trail with actor identity, timestamp, and action type.

#### G. Observability

- **FR-031**: The capability registry MUST expose a liveness dashboard endpoint showing all registered agents, their current status, last heartbeat time, and declared skills.
- **FR-032**: The system MUST emit a structured event for each capability-based assignment decision, including: ticket ID, required capabilities, matched agent, confidence scores, and whether the decision was capability-matched or fallback.
- **FR-033**: Consultation latency (time from request submission to response delivery) MUST be tracked per capability type and surfaced as an operational metric.
- **FR-034**: When a ticket's working memory grows beyond a configurable size threshold, the system MUST emit a warning event to flag potential runaway collaboration loops.

### Key Entities

- **AgentCapabilityRecord**: An agent's declared identity in the registry. Contains: role ID, display name, skill set (list of named skills with confidence 0–100), technology affinities, FSM state ownership, availability status, last heartbeat timestamp, version.
- **CapabilityQuery**: A request to the registry for agents matching a skill and minimum confidence. Returns: matching agents ranked by confidence, filtered by availability status.
- **AgentLifecycleEvent**: An immutable record of a status transition for a registered agent. Contains: agent role ID, previous status, new status, reason, timestamp.
- **ConsultationRequest**: A structured inter-agent request. Contains: originating ticket ID, requesting agent role, required capability, question payload, max wait seconds, request ID.
- **ConsultationResponse**: The reply to a consultation request. Contains: request ID, responding agent role, answer payload, timestamp, status (answered, no_peer, timeout, error).
- **WorkingMemoryEntry**: A single append-only entry in a ticket's shared workspace. Contains: ticket ID, author role ID, entry type (finding, question, response, artifact), content, timestamp, sequence number.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Capability-matched assignment decisions are logged in the audit trail for 100% of ticket assignments within 6 months of rollout, with zero silent fallbacks.
- **SC-002**: The rate of failed runs due to capability mismatch decreases by at least 40% within 3 months of deploying the capability registry and lifecycle model.
- **SC-003**: Agent availability status in the registry reflects actual runtime state within 90 seconds of any agent status change (startup, shutdown, crash), measured end-to-end.
- **SC-004**: Consultation requests between agents are completed (response delivered or "no peer" returned) within 60 seconds in 95% of cases under normal load.
- **SC-005**: Zero cross-ticket data leakage incidents: working memory and consultation responses are verifiably scoped to their originating ticket in all audit records.
- **SC-006**: Operators can determine the full assignment rationale for any ticket within the past 30 days by querying the audit trail — no manual log scraping required.
- **SC-007**: The capability registry falls back gracefully to static assignment in 100% of cases when the registry is unreachable, with no dropped tickets and a degraded-mode audit entry for every such decision.

---

## Clarifications

### Session 2026-06-28

- Q: Where is live capability registry state (availability, heartbeats) stored? → A: New table(s) in `df_dispatcher` (agent-dispatcher's existing PostgreSQL DB). YAML remains the static capability declaration source; the DB holds runtime availability and heartbeat state. No new service required.
- Q: What is the inter-agent consultation transport protocol? → A: Synchronous HTTP request-response mediated by `agent-dispatcher`. The requesting agent POSTs to `agent-dispatcher`, which forwards to the peer and returns the response in the same HTTP call with a server-side timeout.
- Q: What is the persistent worker runtime shape? → A: Logical persistence only. A registration and heartbeat record in `df_dispatcher` tracks each agent worker instance; the underlying execution remains process-per-ticket as today. No long-running process management required.
- Q: Which service owns shared working memory? → A: `agent-dispatcher` owns working memory in `df_dispatcher`. The Orchestrator reads it via `agent-dispatcher`'s HTTP API at gate time. `context-distiller` continues to own distilled project memory after ticket closure.
- Q: Who resolves capability-based assignment — Orchestrator or Dispatcher? → A: Orchestrator specifies required capabilities in the job payload; Dispatcher is the sole resolver, querying its own registry and returning the matched capability record to the Orchestrator in the result payload for audit. Orchestrator never calls the registry directly.

---

## Assumptions

- The existing Keycloak identity provider and service credential pattern will be extended to issue scoped tokens for inter-agent communication; no new identity provider is introduced.
- Agents are identified by their existing `role_id` values; no new identifier scheme is required.
- The capability registry is an extension of the existing `CapabilityRegistry` component in `agent-dispatcher`, backed by new tables in `df_dispatcher` for runtime state (availability, heartbeats, logical worker records) and retaining YAML as the static declaration source; it does not require a new standalone service for the first maturity phase.
- "Persistent agent runtime" means a persistent logical registration record in `df_dispatcher`, not a long-running process; the underlying execution model (process-per-ticket) is unchanged.
- Shared working memory for active tickets is owned by `agent-dispatcher` and persisted in `df_dispatcher`. The Orchestrator accesses it via `agent-dispatcher`'s HTTP API at gate evaluation time. On ticket closure, a distillation job may promote relevant entries into `context-distiller`'s project memory as it does today for other artifacts.
- Consultation routing is coordinator-mediated (through `agent-dispatcher`) in the first phase; true peer-to-peer messaging without a coordinator is explicitly out of scope.
- FSM sovereignty remains entirely with Orchestrator; neither the capability registry nor the inter-agent layer can initiate FSM transitions.
- Backward compatibility: all existing brainstorm and single-agent execution flows continue to operate unchanged when capability registry or peer consultation features are absent or disabled.
- The rollout uses feature flags to allow per-environment opt-in; production enablement is gated on passing all acceptance criteria in a staging environment.
- Mobile/browser UI changes are out of scope; this feature is entirely backend and agent-runtime facing.
