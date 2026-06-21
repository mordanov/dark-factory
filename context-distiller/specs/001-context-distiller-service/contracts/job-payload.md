# Job Payload Contract: Distill Job

The Orchestrator writes this structure into `jobs.payload` (JSONB) when enqueuing
a `distill` job. ContextDistiller reads and validates this payload before calling
the DataCollector.

---

## Payload Schema

```json
{
  "ticket_id": "TICKET-042",
  "project_id": "my-project",
  "audit_trail": [
    {
      "action": "ADVANCE",
      "from_state": "testing",
      "to_state": "release",
      "details": "Test coverage ≥80% confirmed",
      "assigned_agent": "autotester",
      "created_at": "2026-06-20T11:00:00Z"
    }
  ],
  "ticket_snapshot": {
    "title": "Add refresh token support",
    "description": "...",
    "ticket_type": "feature",
    "tags": ["auth", "backend"],
    "fsm_status": "done"
  }
}
```

## Field Rules

| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| ticket_id | Yes | — | Used as primary key for TM API fetch |
| project_id | Yes | — | Used as MongoDB document _id |
| audit_trail | No | [] | If empty, distillation proceeds with reduced context |
| ticket_snapshot | No | {} | If absent/minimal, DataCollector falls back to TM API |
| ticket_snapshot.fsm_status | No | null | Should be "done" but not enforced by worker |

## DataCollector Behaviour

1. Always fetch the full ticket from TM API using `ticket_id` — the snapshot
   in the payload is a fallback only (used if TM API is unreachable: job fails,
   not degrades).
2. Audit trail in payload is supplemented (not replaced) by `audit_log` table
   entries for the same `ticket_id`.
3. Current project_memory is fetched from MongoDB, not from the payload.
4. ADR IDs and titles are fetched from `adrs` collection for context injection.
