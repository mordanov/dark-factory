# Companion `/speckit-clarify` question set (missing areas)

Use this as the argument/context when running `/speckit-clarify`, then answer using the predefined options below.

## 1) Paste into `/speckit-clarify`

```text
Prioritize only high-impact ambiguities for feature: multi-agent maturity phase.
Focus questions on:
1) inter-agent protocol shape,
2) persistent worker lifecycle,
3) capability registry source-of-truth.

Optimization goals:
- preserve existing orchestrator FSM sovereignty,
- keep backward compatibility with current dispatcher-driven brainstorm flow,
- enforce auditable deterministic assignment decisions,
- avoid cross-service DB access,
- keep service boundaries over HTTP.

Ask at most 5 questions, and prefer architecture-impact decisions over implementation-detail questions.
```

## 2) Pre-resolve question set (answer these during clarify)

### Q1. Inter-agent protocol authority model
**Recommended:** **B** - Keeps orchestration control centralized while enabling limited direct collaboration.

| Option | Description |
|--------|-------------|
| A | Orchestrator-brokered only; no direct agent requests |
| B | Hybrid: orchestrator policy + dispatcher-mediated direct request/response |
| C | Fully peer-to-peer agent messaging with minimal central mediation |

**Preferred answer:** `B`

---

### Q2. Message pattern and delivery guarantees
**Recommended:** **A** - Request/response with idempotency and timeout is the smallest safe step with clear failure semantics.

| Option | Description |
|--------|-------------|
| A | Synchronous request/response over HTTP + idempotency key |
| B | Async queued messaging with at-least-once delivery |
| C | Event bus pub/sub with eventual consistency only |

**Preferred answer:** `A`

---

### Q3. Persistent worker lifecycle contract
**Recommended:** **B** - Adds robust operations (leases, heartbeats, draining) without introducing global scheduler complexity.

| Option | Description |
|--------|-------------|
| A | Stateless ephemeral runs only |
| B | Persistent workers with lease + heartbeat + drain states |
| C | Kubernetes-style reconciliation loop with controller ownership |

**Preferred answer:** `B`

---

### Q4. Capability registry source of truth
**Recommended:** **C** - Database-backed registry enables runtime updates and auditable history; YAML can remain bootstrap input.

| Option | Description |
|--------|-------------|
| A | Static YAML in repo only |
| B | Context Distiller documents only |
| C | Dedicated registry tables in Agent Dispatcher DB (+ optional YAML bootstrap) |

**Preferred answer:** `C`

---

### Q5. Assignment determinism and fallback policy
**Recommended:** **A** - Deterministic scoring with explicit fallback keeps behavior auditable and avoids regressions.

| Option | Description |
|--------|-------------|
| A | Deterministic weighted scoring; fallback to current LLM heuristic |
| B | LLM-first assignment; registry used as advisory metadata |
| C | Manual rules-only mapping by ticket type |

**Preferred answer:** `A`

## 3) Output constraints to enforce during clarification

- Require measurable acceptance signals for protocol latency, worker health, and assignment explainability.
- Require explicit API contracts among `orchestrator`, `agent-dispatcher`, `agent-tools`, and `context-distiller`.
- Require migration strategy that keeps current brainstorm loop functional during rollout.
- Require security decisions: service auth, scope boundaries, and audit log requirements.

