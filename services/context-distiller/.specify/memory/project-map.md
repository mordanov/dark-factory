# Dark Factory — Project Map

## Boundary rule
Read sibling projects at `../` level only. You are allowed to read any files in those sibling projects for context. You are advised to look into defined folders below at first.
Never traverse above `../`. Other projects there are unrelated.

## Sibling projects

### Ticket Manager (`../ticket-manager/`)
- API contracts: `src/routes/` or `src/api/`
- Data models: `src/models/`
- Key fact: ContextDistiller reads tickets via TM API (read-only).
  Never writes to TM except via the service account.

### Prompt Studio (`../user-input-manager/`)
- Schemas: `backend/src/schemas/schemas.py`
- JWT issued here — ContextDistiller only validates, never issues
- Orchestrator proxy: `backend/src/api/v1/orchestrator.py`

### Orchestrator (`../orchestrator/`)
- Job table schema: `src/models/models.py`
- API contracts: `src/api/`
- FSM states: `src/services/fsm/engine.py`
- ContextDistiller reads jobs from this table, never owns the schema
