# Quickstart: Agent Maturity Platform

**Branch**: `003-agent-maturity` | **Phase**: 1

Integration scenarios for developers implementing or testing this feature.

---

## Scenario 1: Capability-Based Assignment (P1)

**Goal**: Orchestrator triggers a backend run specifying required capabilities; Dispatcher resolves and assigns the best-matched idle worker.

### Prerequisites
- `agent-dispatcher` running with migration 0002 applied
- `backend` agent registered as idle worker (see Scenario 2)
- YAML registry loaded with `backend` agent including `python_backend` capability

### Flow

**Step 1** — Orchestrator derives capabilities and triggers the run:
```http
POST /api/v1/runs
Authorization: Bearer <service-token>
Content-Type: application/json

{
  "ticket_id": "TICKET-123",
  "to_state": "backend_development",
  "context": { ... },
  "registry_yaml": "...",
  "required_capabilities": ["python_backend", "fastapi"]
}
```

**Step 2** — Dispatcher resolves the assignment:
- Queries `agent_worker_records WHERE status = 'idle' AND role_id IN (registry matches)`
- Selects `backend` worker with highest confidence for `python_backend` + `fastapi`
- Marks worker `status = 'busy'`
- Writes `assigned` lifecycle event

**Step 3** — Run completes; result includes matched record:
```json
{
  "status": "completed",
  "summary": "...",
  "matched_capability_record": {
    "role_id": "backend",
    "capabilities": ["python_backend", "fastapi", "postgresql"],
    "confidence": {"python_backend": 95, "fastapi": 90}
  }
}
```

**Step 4** — Worker status returns to `idle`.

### Fallback Verification
Send the same request with no available idle `backend` worker. Confirm:
- Run still proceeds (falls back to static assignment)
- `matched_capability_record = null` in the result

---

## Scenario 2: Worker Lifecycle (P2)

**Goal**: Simulate a complete worker lifecycle — register, heartbeat, drain, offline.

### Register
```http
POST /api/v1/workers/register
Authorization: Bearer <service-token>
Content-Type: application/json

{
  "role_id": "backend",
  "version": "1.0.0",
  "capabilities_snapshot": {"python_backend": 95, "fastapi": 90}
}
```
→ Response 201 with `worker_id`.

### Send Heartbeats
```http
POST /api/v1/workers/backend/heartbeat
Authorization: Bearer <service-token>
Content-Type: application/json

{
  "worker_id": "<worker_id>",
  "status": "idle"
}
```
→ Response 200 with `next_heartbeat_deadline`.

### List Workers
```http
GET /api/v1/workers?status=idle
Authorization: Bearer <service-token>
```
→ Confirm `backend` appears with `status: idle`.

### Drain
```http
POST /api/v1/workers/backend/drain
Authorization: Bearer <service-token>
Content-Type: application/json

{"worker_id": "<worker_id>"}
```
→ Response 200 with `status: draining`.

### Verify Liveness Sweep
Stop sending heartbeats. After ~2 minutes, query `GET /api/v1/workers?role_id=backend` — confirm `status: offline`.

### Audit Trail
```http
GET /api/v1/workers/<worker_id>/events  (if implemented)
```
Verify event sequence: `registered` → `heartbeat` → `drain_requested` → `offline_liveness`.

---

## Scenario 3: Peer Consultation (P3)

**Goal**: `software-architect` agent asks `security-architect` a domain question during execution.

### Prerequisites
- `security-architect` registered as idle worker
- Both agents have service tokens

### Execute Consultation
```http
POST /api/v1/consult
Authorization: Bearer <software-architect-token>
Content-Type: application/json

{
  "requesting_role_id": "software-architect",
  "run_id": "550e8400-e29b-41d4-a716-446655440001",
  "ticket_id": "TICKET-456",
  "required_peer_capabilities": ["security_assessment"],
  "question": "Should tenant isolation use RLS or application-layer filtering?",
  "context_summary": "PostgreSQL 16, JWT auth, 10k tenants.",
  "timeout_seconds": 60
}
```

→ Response 200 with `answer` from `security-architect`.

### Verify Working Memory Auto-Write
```http
GET /api/v1/working-memory/TICKET-456?entry_type=question
```
→ Entry with `author_role_id: software-architect` and `tags: ["consultation"]`.

```http
GET /api/v1/working-memory/TICKET-456?entry_type=answer
```
→ Entry with `author_role_id: security-architect` and `tags: ["consultation"]`.

---

## Scenario 4: Shared Working Memory (P4)

**Goal**: Two agents write observations; Orchestrator reads them at the next gate.

### Backend Agent Writes
```http
POST /api/v1/working-memory/TICKET-789
Authorization: Bearer <backend-token>
Content-Type: application/json

{
  "run_id": "550e8400-e29b-41d4-a716-446655440003",
  "author_role_id": "backend",
  "entry_type": "observation",
  "content": "Existing auth module uses 1-hour JWT expiry with no refresh.",
  "tags": ["auth", "security"]
}
```

### Code-Reviewer Agent Writes
```http
POST /api/v1/working-memory/TICKET-789
Authorization: Bearer <reviewer-token>
Content-Type: application/json

{
  "run_id": "550e8400-e29b-41d4-a716-446655440004",
  "author_role_id": "code-reviewer",
  "entry_type": "decision",
  "content": "Recommend implementing refresh tokens before next sprint.",
  "tags": ["auth", "recommendation"]
}
```

### Orchestrator Reads at Gate
```http
GET /api/v1/working-memory/TICKET-789
Authorization: Bearer <orchestrator-token>
```
→ Both entries returned in chronological order.

### Cross-Ticket Isolation Test
Attempt to write to `TICKET-789` using a `run_id` that belongs to `TICKET-000`.
→ Response 403.

---

## Running the Full Test Suite

```bash
cd services/agent-dispatcher

# Unit tests only (no DB required)
pytest tests/unit/ -v

# Integration tests (requires running PostgreSQL with df_dispatcher)
pytest tests/integration/ -v --cov --cov-fail-under=80

# Run a specific scenario
pytest tests/integration/test_capability_assignment.py -v
pytest tests/integration/test_worker_lifecycle.py -v
pytest tests/integration/test_consultation.py -v
pytest tests/integration/test_working_memory.py -v
```
