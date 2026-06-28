# Contract: Peer Consultation API

**Service**: `agent-dispatcher`  
**Base path**: `/api/v1`  
**Auth**: Keycloak service token (agent service account)

---

## POST /api/v1/consult

Submit a synchronous peer consultation request. The requesting agent asks a domain question; `agent-dispatcher` identifies the best available peer, forwards the question, and returns the response — all within the same HTTP call.

**Request**:
```json
{
  "requesting_role_id": "software-architect",
  "run_id": "550e8400-e29b-41d4-a716-446655440001",
  "ticket_id": "TICKET-123",
  "required_peer_capabilities": ["security_assessment"],
  "question": "Should we use row-level security or application-layer filtering for tenant isolation?",
  "context_summary": "Multi-tenant SaaS app, PostgreSQL 16, existing auth via JWT.",
  "timeout_seconds": 60
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `requesting_role_id` | string | Yes | Role ID of the calling agent |
| `run_id` | UUID | Yes | The run this consultation is associated with |
| `ticket_id` | string | Yes | The ticket this consultation is about |
| `required_peer_capabilities` | `list[string]` | Yes | Capabilities the peer must have |
| `question` | string | Yes | The domain question (max 2,048 chars) |
| `context_summary` | string | No | Brief background for the peer (max 1,024 chars) |
| `timeout_seconds` | integer | No | Response deadline (default: 60, max: 120) |

**Response 200**:
```json
{
  "consultation_id": "550e8400-e29b-41d4-a716-446655440002",
  "peer_role_id": "security-architect",
  "answer": "Row-level security is preferred for true multi-tenant isolation...",
  "peer_capability_record": {
    "role_id": "security-architect",
    "capabilities": ["security_assessment", "threat_modeling"]
  },
  "latency_ms": 4200
}
```

**Response 404**: No available peer with the required capabilities  
**Response 408**: Peer did not respond within `timeout_seconds`  
**Response 400**: Invalid request (empty question, unknown capabilities)  
**Response 401**: Missing or invalid service token

---

## Consultation Resolution Algorithm

1. Resolve peer: `CapabilityRegistry.get_by_capability(required_peer_capabilities)` → filter to currently-idle workers
2. If no peer available: return 404 immediately (do not queue)
3. Select best-matched peer (same ranking as capability-based assignment)
4. Forward question to peer agent runner with `asyncio.wait_for(timeout=timeout_seconds)`
5. Peer agent processes question and returns a text answer
6. Record consultation: write `WorkingMemoryEntry` for both question (by requester) and answer (by peer) with `entry_type = 'question'` / `'answer'`
7. Return response to caller

**Scope**: The forwarded call is a targeted question prompt to the peer agent, not a full ticket execution. The peer agent returns a text answer only; no FSM state changes, no artifact generation.

**Peer isolation**: A consultation does NOT change the peer's `AgentWorkerRecord.status` — it is treated as a lightweight side call. If the peer is simultaneously executing a run (status `busy`), the consultation is either queued for 5 seconds or rejected with 404 depending on a configurable flag (`consultation_queue_when_busy`, default: `false`).

---

## Working Memory Auto-Write

Successful consultations automatically produce two `WorkingMemoryEntry` rows:

```
entry_type=question: author=requesting_role_id, content=question, tags=["consultation"]
entry_type=answer:   author=peer_role_id, content=answer, tags=["consultation"]
```

These entries are retrievable via `GET /api/v1/working-memory/{ticket_id}` and are visible to the Orchestrator at the next gate.

---

## Error Response Shape

```json
{
  "detail": "No available peer with capabilities ['security_assessment']"
}
```
