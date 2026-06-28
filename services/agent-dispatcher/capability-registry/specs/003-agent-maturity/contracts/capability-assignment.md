# Contract: Capability-Based Assignment

**Services**: `orchestrator` → `agent-dispatcher`  
**Context**: Extends the existing run trigger flow

---

## Modified Request: POST /api/v1/runs (existing endpoint)

The existing run-trigger payload is extended with one new optional field.

**Diff from current schema**:
```json
{
  "ticket_id": "TICKET-123",
  "to_state": "backend_development",
  "context": { "...existing fields..." },
  "registry_yaml": "version: '1.0'\nagents: [...]",
  "required_capabilities": ["python_backend", "fastapi"]
}
```

| Field | Type | Required | Behavior change |
|-------|------|----------|----------------|
| `required_capabilities` | `list[string]` | No | **NEW** — empty list = existing static assignment; non-empty list = capability-based resolution |

**Backward compatibility**: The field defaults to `[]`. All existing callers sending the old payload continue to work unchanged. The Dispatcher falls back to static role-based assignment when the list is empty or the registry returns no match.

---

## Modified Response: AgentResult (existing schema)

The existing result payload gains one new optional field in the `artifacts` / top-level result.

**Diff from current schema**:
```json
{
  "status": "completed",
  "summary": "...",
  "artifacts": [],
  "tm_comment": "...",
  "brainstorm_consensus": null,
  "errors": [],
  "matched_capability_record": {
    "role_id": "backend",
    "display_name": "Backend Engineer",
    "capabilities": ["python_backend", "fastapi", "postgresql"],
    "confidence": {"python_backend": 95, "fastapi": 90},
    "coordinator": false
  }
}
```

| Field | Type | Nullability | Notes |
|-------|------|-------------|-------|
| `matched_capability_record` | object | nullable | **NEW** — null when capability-based assignment was not used |

---

## Assignment Resolution Algorithm

When `required_capabilities` is non-empty:

1. Load YAML registry (`CapabilityRegistry.get_by_capability(required_capabilities, min_confidence=70)`)
2. Filter by availability: query `agent_worker_records WHERE status = 'idle' AND role_id IN (step 1 matches)`
3. Rank by: (a) count of required capabilities met, (b) average confidence for those capabilities
4. Select the highest-ranked available worker; if tie, pick the one with the earliest `registered_at`
5. If no available worker found: fall back to static assignment (current behavior) and log a warning
6. Mark selected worker `status = 'busy'`, write `assigned` lifecycle event
7. Proceed with existing job spawn
8. Return `matched_capability_record` in result payload

**Failure modes**:
- Registry unavailable: fall back to static assignment, `matched_capability_record = null`
- No capable worker available: fall back to static assignment, `matched_capability_record = null`
- Assignment failure does NOT block ticket processing (graceful degradation, FR-016)

---

## Capability Specification Derivation (Orchestrator Side)

The Orchestrator derives `required_capabilities` from the FSM transition context:

```python
# Pseudo-code in orchestrator/src/services/dispatcher_client.py
def derive_required_capabilities(to_state: str, ticket_tags: list[str]) -> list[str]:
    # State → base capability mapping
    STATE_CAPABILITIES = {
        "backend_development": ["python_backend"],
        "frontend_development": ["typescript_frontend"],
        "security_review": ["security_assessment"],
        # ... etc
    }
    base = STATE_CAPABILITIES.get(to_state, [])
    # Ticket tags can add specifics (e.g., tag "fastapi" → add "fastapi" capability)
    tag_extras = [t for t in ticket_tags if t in KNOWN_CAPABILITY_NAMES]
    return list(dict.fromkeys(base + tag_extras))  # deduped, order-preserving
```

This mapping lives in the Orchestrator, preserving FSM sovereignty. The Dispatcher does not interpret `to_state`.

---

## Contract Tests (to be implemented in Phase 2)

| Test | Assertion |
|------|-----------|
| Empty `required_capabilities` | Dispatcher uses static assignment; `matched_capability_record = null` |
| Single required capability, one match | Returns correct `matched_capability_record` |
| Multiple required capabilities, partial match | Selects agent with highest capability coverage |
| No available worker (all busy) | Fallback to static; `matched_capability_record = null` |
| Unknown capability name | Fallback to static; `matched_capability_record = null` |
| Old payload format (no field) | Identical to empty list behavior |
