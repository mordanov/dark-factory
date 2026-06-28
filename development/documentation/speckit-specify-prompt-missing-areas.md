# Prompt for `/speckit-specify`: Close Missing Architecture Areas

Use the following prompt with `/speckit-specify`.

```text
Create a new feature spec that closes the known implementation gaps documented in:
- development/documentation/dark-factory-architecture.md
- development/documentation/services-implementation-status.md

Feature intent:
Implement the next maturity phase for Dark Factory multi-agent execution by addressing three gaps:
1) limited inter-agent communication depth,
2) non-persistent (transient) agent runtime model,
3) limited capability discovery for assignment decisions.

Context and constraints:
- This is a distributed six-service monorepo with strict service boundaries over HTTP.
- Ticket FSM sovereignty must remain in Orchestrator (Agent Dispatcher must not mutate FSM directly).
- Existing runtime services and databases must stay compatible with current workflows.
- Follow constitution constraints in .specify/memory/constitution.md (especially service isolation, auth, deployment, and dispatcher safety rules).
- Prefer additive, backward-compatible changes with explicit migration paths.

Please produce a complete feature specification including:
- Problem statement and business value.
- Goals and non-goals.
- User stories / operational scenarios.
- Functional requirements for:
  A. Agent-to-agent collaboration protocol (coordinator-mediated and optional direct request/response patterns).
  B. Shared working memory model for mid-task artifacts and peer visibility.
  C. Persistent agent worker runtime model (lifecycle, heartbeats, availability, draining, failure recovery).
  D. Capability registry (declared capabilities, technology affinities, confidence, availability, versioning).
  E. Assignment decision contract between Orchestrator, Dispatcher, and capability registry.
- API and event contract changes across impacted services.
- Data model changes (PostgreSQL/MongoDB) and migration strategy.
- Security model for inter-agent communication (authn/authz, scope limits, auditability).
- Observability requirements (metrics, traces, audit logs, SLO-style signals).
- Rollout plan with feature flags and compatibility phases.
- Risks, alternatives considered, and open questions.
- Acceptance criteria and measurable Definition of Done.

Cross-service impact to evaluate explicitly:
- services/orchestrator
- services/agent-dispatcher
- services/agent-tools
- services/context-distiller
- services/ticket-manager (only if needed for visibility/audit extensions)

Design expectations:
- Keep existing completed flows intact (prompt processing, planning, decomposition, orchestration loop).
- Preserve current brainstorm behavior while extending collaboration capabilities.
- Make capability-based assignment deterministic and auditable, with graceful fallback to current behavior.
- Ensure no regression of current auth architecture (Keycloak, client credentials, service boundaries).

Output quality bar:
- Specification must be implementation-ready and dependency-aware.
- Requirements must be testable and unambiguous.
- Include explicit backward-compatibility and migration acceptance checks.
- Call out any constitution conflicts; if conflicts are found, list required constitution amendments clearly.
```

