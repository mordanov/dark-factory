# Feature Specification: Agent Dispatcher Service

**Feature Branch**: `002-agent-dispatcher`
**Created**: 2026-06-22
**Status**: Draft
**Input**: User description: "Build the Agent Dispatcher service for Dark Factory. This service detects agent assignments made by the Orchestrator, executes agents (Claude Code subprocess or direct API call), coordinates brainstorm sessions, and reports results back to the Ticket Manager and Orchestrator."

## Clarifications

### Session 2026-06-22

- Q: Should `services/agent-dispatcher/README.md` be a required deliverable? → A: Yes — README.md required, covering setup, env vars, runner modes, and API reference (written as the final task in the implementation phase).
- Q: How should orphaned `running` records (left by a crashed process) be handled on service restart? → A: Startup sweep — atomically transition all `running` records to `needs_review` with error_message "Service restarted; run orphaned", then trigger Orchestrator for each affected ticket.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Agent Execution (Priority: P1)

When the Orchestrator assigns an agent to a ticket, the system must automatically detect
the assignment and execute the correct agent within a bounded time. The internal developer
(operator) running the system needs assurance that tickets progress without manual
intervention once an assignment is made.

**Why this priority**: This is the core value of the service. Without it, the entire
Dark Factory automation pipeline stalls at every agent handoff.

**Independent Test**: A ticket with `assigned_agent = "backend"` is created in Ticket
Manager. Within `POLL_INTERVAL_SECONDS` the Dispatcher detects it and begins a run. The
run is recorded with `status = running`. When the agent completes, the run transitions
to `completed` and a comment appears on the TM ticket.

**Acceptance Scenarios**:

1. **Given** a ticket with `assigned_agent = "backend"` exists in the Orchestrator's
   pending-tickets list, **When** the polling interval elapses, **Then** the Dispatcher
   creates an `agent_runs` record with `status = running` and begins agent execution.
2. **Given** an agent run completes with a valid `[RESULT]` block, **When** the result is
   parsed, **Then** `agent_runs` is updated to `status = completed`, the TM ticket receives
   the `tm_comment` as a new comment, and a new Orchestrator evaluation job is triggered.
3. **Given** a ticket is already `status = running` in `agent_runs`, **When** the poller
   finds it again, **Then** no second run is started and the ticket is skipped.

---

### User Story 2 - Graceful Handling of Agent Failures (Priority: P2)

When an agent times out, crashes, or produces no parseable output, the system must record
the failure, notify the Ticket Manager, and re-trigger the Orchestrator so the FSM can
decide the next step — without crashing the Dispatcher or blocking other tickets.

**Why this priority**: Without graceful failure handling, a single bad agent run would
stall the entire system. The Orchestrator must always know what happened so the FSM can
recover.

**Independent Test**: An agent run is configured to produce no `[RESULT]` block (raw text
only). The Dispatcher records `status = needs_review`, posts the raw output as a TM
comment (truncated to 2000 chars), and triggers an Orchestrator job. No crash occurs.

**Acceptance Scenarios**:

1. **Given** an agent process exits with code 0 but produces no `[RESULT]` block,
   **When** the output is parsed, **Then** the run is marked `needs_review` and the raw
   stdout (≤ 2000 chars) is posted as the TM comment.
2. **Given** an agent run exceeds its configured timeout, **When** the timeout fires,
   **Then** the run is marked `timed_out`, the TM ticket is commented, and the Orchestrator
   is triggered with error context.
3. **Given** an agent's system prompt file is missing from `AGENT_PROMPTS_DIR`, **When**
   the Dispatcher attempts the run, **Then** the run is marked `failed`, the TM ticket
   is commented with the error, and the Orchestrator is triggered. The Dispatcher service
   itself continues running.

---

### User Story 3 - Multi-Agent Brainstorm Coordination (Priority: P3)

For architecture-review tickets, multiple specialist agents must review the problem
sequentially before the Orchestrator makes a final decision. Each agent must see what
prior agents said. The Dispatcher coordinates this multi-round session and concludes it
when consensus is reached or the round limit is hit.

**Why this priority**: Architecture review is a high-value but lower-frequency flow.
P1 and P2 must work first since brainstorm depends on the single-agent execution path.

**Independent Test**: A ticket with `ticket_type = architecture_review` is assigned.
Two agents (`software_architect`, `security_architect`) run sequentially in the same
brainstorm session. Both share the same `BRAINSTORM_PROJECT` name in their context.
If the first agent's result contains `"brainstorm_consensus": "agreed"`, the second
agent is not invoked and the session concludes immediately.

**Acceptance Scenarios**:

1. **Given** an `architecture_review` ticket is assigned, **When** the Dispatcher
   processes it, **Then** it runs `BRAINSTORM_AGENTS` sequentially (not in parallel),
   each with the same `df-{ticket_id}` brainstorm project name in their context.
2. **Given** the first brainstorm agent returns `"brainstorm_consensus": "agreed"`,
   **When** the result is parsed, **Then** the session concludes immediately and
   subsequent agents in the round are not invoked.
3. **Given** `BRAINSTORM_MAX_ROUNDS` is reached without consensus, **When** the final
   round completes, **Then** the session is concluded with `consensus = null` and the
   Orchestrator is triggered with the aggregated results.
4. **Given** `AGENT_RUNNER_MODE = api`, **When** the second brainstorm agent runs,
   **Then** the first agent's `tm_comment` is injected into the second agent's context
   as "Previous agent responses:" — brainstorm-mcp is not used in API mode.

---

### Edge Cases

- What happens when the Orchestrator API is unreachable during polling? The poller logs
  the failure, skips the cycle, and retries on the next poll interval.
- What happens when the TM comment POST fails after a run completes? The failure is
  logged and the Orchestrator trigger still proceeds (graceful degradation).
- What happens when `WORKER_MAX_CONCURRENT_RUNS` tickets are all running and a new
  one is detected? The new ticket waits in the async queue behind the semaphore; it is
  not dropped.
- What happens when the same ticket appears in multiple consecutive poll cycles while
  running? `has_running` returns true and the ticket is skipped each time.
- What happens when the service restarts while agent runs are in progress? On startup the
  service sweeps `agent_runs` for `running` records, marks them `needs_review` with an
  "orphaned" error message, and re-triggers the Orchestrator for each — ensuring no
  ticket is permanently blocked by a stale lock.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST poll the Orchestrator for tickets with `assigned_agent` set,
  at an interval configurable via `POLL_INTERVAL_SECONDS`.
- **FR-002**: The system MUST support two agent runner modes: `claude_code` (subprocess)
  and `api` (direct LLM call), selectable at startup via `AGENT_RUNNER_MODE`.
- **FR-003**: The system MUST enforce that at most one agent run is active per ticket at
  any time, using the `agent_runs` table as the source of truth.
- **FR-004**: The system MUST read agent system prompts from disk on each run (no caching)
  from `AGENT_PROMPTS_DIR/{agent_id}.md`.
- **FR-005**: The system MUST parse the `[RESULT]...[/RESULT]` block from agent stdout
  and extract `status`, `summary`, `artifacts`, `tm_comment`, `brainstorm_consensus`,
  and `errors`.
- **FR-006**: The system MUST handle missing or invalid `[RESULT]` blocks gracefully:
  treat as `needs_review`, use raw stdout as the comment, and never crash.
- **FR-007**: The system MUST enforce per-agent-type timeouts, configurable via
  `AGENT_TIMEOUT_{AGENT_ID_UPPER}` with fallback to `AGENT_TIMEOUT_DEFAULT`.
- **FR-008**: The system MUST post a comment to the TM ticket and trigger a new
  Orchestrator evaluation after every completed, failed, or timed-out run.
- **FR-009**: The system MUST NEVER modify Orchestrator FSM state directly.
- **FR-010**: The system MUST coordinate multi-agent brainstorm sessions for
  `architecture_review` tickets, running agents sequentially and supporting early
  exit on consensus.
- **FR-011**: The system MUST persist all run records in the `agent_runs` table with
  full context snapshot, raw output, and parsed result.
- **FR-012**: The system MUST limit concurrent runs via a configurable semaphore
  (`WORKER_MAX_CONCURRENT_RUNS`) without blocking the polling loop.
- **FR-013**: The system MUST NEVER include `SERVICE_JWT` or TM service credentials
  in logs, run records, or API responses.
- **FR-014**: The system MUST expose `GET /api/v1/runs` and `GET /api/v1/runs/{id}`
  endpoints for run history inspection, protected by Bearer auth.
- **FR-015**: The system MUST expose `GET /api/health` returning runner mode and
  service status.
- **FR-017**: On service startup, the system MUST scan `agent_runs` for any records with
  `status = running` and transition them to `needs_review` with
  `error_message = "Service restarted; run orphaned"`, then trigger a new Orchestrator
  evaluation for each affected ticket. This prevents orphaned records from permanently
  blocking the double-run guard.
- **FR-016**: The service MUST ship a `README.md` at `services/agent-dispatcher/README.md`
  covering: prerequisites, environment variables, runner modes, how to run in isolation
  and as part of the monorepo, how to run tests, and the full API endpoint reference.

### Key Entities

- **AgentRun**: Represents one execution of an agent for a ticket. Tracks ticket ID,
  agent ID, runner mode, status lifecycle, context snapshot, raw output, parsed result,
  timing, and brainstorm session linkage.
- **BrainstormSession**: Tracks a multi-round brainstorm for one ticket. Records project
  name, current round, max rounds, status (`active`/`concluded`), and final consensus
  (`agreed`/`disagreed`/null).
- **AgentResult**: The structured output parsed from an agent's `[RESULT]` block.
  Contains status, summary, artifacts list, TM comment, brainstorm consensus signal,
  and errors list.
- **AgentContext**: The full markdown document passed to an agent as its task input.
  Assembled from ticket data, project memory, ADRs, agent config, brainstorm session
  state, and TM access credentials.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A ticket with `assigned_agent` set is detected and a run begins within
  `POLL_INTERVAL_SECONDS + 5` seconds of the assignment being made.
- **SC-002**: A completed agent run (with valid `[RESULT]`) results in a TM comment
  and an Orchestrator trigger within 10 seconds of the agent process exiting.
- **SC-003**: The service sustains `WORKER_MAX_CONCURRENT_RUNS` simultaneous agent
  runs without the polling loop stalling or missing new assignments.
- **SC-004**: A missing or malformed `[RESULT]` block is handled without service
  interruption in 100% of cases — no crashes, no orphaned running records.
- **SC-009**: After a service restart, all previously-`running` records are resolved
  to `needs_review` within the first poll cycle, and an Orchestrator trigger is fired
  for each — zero tickets permanently blocked by a stale lock.
- **SC-005**: Brainstorm sessions with two agents and early consensus complete in
  fewer elapsed wall-clock seconds than running both agents unconditionally.
- **SC-006**: All unit tests achieve ≥ 80% line and function coverage with zero
  real Claude Code or API calls made during the test suite.
- **SC-007**: `AUTH_MODE=local` behaviour is functionally identical to the pattern
  established by other Dark Factory services.
- **SC-008**: `services/agent-dispatcher/README.md` exists and covers all required
  sections (env vars, runner modes, test invocation, API reference) as the final
  deliverable of the implementation phase.

## Assumptions

- The Orchestrator exposes a `GET /api/v1/jobs/pending-tickets` endpoint returning
  tickets with `assigned_agent` set; this contract is already implemented.
- The Ticket Manager exposes a POST endpoint for adding comments to tickets at
  `POST /api/projects/{project_id}/tickets/{ticket_id}/comments`.
- The Context Distiller's project-memory, ADR, and agent-config endpoints may return
  404 or be temporarily unavailable; the Dispatcher treats all such failures as
  "empty section" and continues.
- Agent system prompt files for the initial agents (`backend.md`,
  `software_architect.md`, `security_architect.md`, etc.) already exist in the
  prompts directory and are managed outside this service.
- In `claude_code` mode, the `brainstorm` MCP server is already configured in
  `~/.claude/mcp_config.json` and available to Claude Code subprocesses.
- The `agent-tools` MCP server is out of scope for this spec and will be covered
  by a separate implementation.
- Prometheus `/metrics` endpoint is out of scope for v1 (nice-to-have, not required).
- Re-running failed agent runs via manual trigger is out of scope; operators
  re-trigger via the Orchestrator.
- Keycloak integration is out of scope; the auth adapter stub (`AUTH_MODE=local`)
  is the only required auth mode for this phase.
