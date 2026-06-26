# Contract: registry.yaml Schema

**File**: `development/agents/registry.yaml`  
**Consumer**: `CapabilityRegistry.load()` in `agent-dispatcher`  
**Version**: `"1.0"`

---

## Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | `string` | Yes | Schema version. Currently `"1.0"`. |
| `brainstorm_project_template` | `string` | Yes | Python `.format()` template. Must contain `{ticket_id}`. |
| `agents` | `list[AgentEntry]` | Yes | Ordered list of all agent role definitions. |

---

## AgentEntry fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role_id` | `string` | Yes | Hyphenated identifier. Unique across all entries. Must match `run-agents.sh` ROLES array and `VALID_AGENT_IDS` in dispatcher. |
| `display_name` | `string` | Yes | Human-readable name for logs and UI. |
| `skill_file` | `string` | Yes | Filename only (no path). File must exist in `development/agents/`. |
| `coordinator` | `boolean` | No (default: `false`) | True for agents that drive brainstorm sessions. |
| `capabilities` | `list[string]` | No (default: `[]`) | Capability tags. Snake_case. Used in LLM selection prompt. |
| `fsm_ownership` | `list[string]` | No (default: `[]`) | FSM state names this agent owns. Must match state names in `engine.py`. |
| `preferred_for` | `list[string]` | No (default: `[]`) | Keyword hints for LLM selection. Used when multiple agents own the same state. |
| `brainstorm_also_for` | `list[string]` | No (default: `[]`) | FSM states where this agent participates in brainstorm without owning the state. |
| `brainstorm_role` | `string` | No (default: `"contributor"`) | `"coordinator"` or `"contributor"`. |

---

## Invariants (enforced by `CapabilityRegistry.load()`)

1. All `role_id` values must be unique.
2. All `fsm_ownership` state names must be non-empty strings.
3. `brainstorm_role` must be `"coordinator"` or `"contributor"` — no other values.
4. At most one agent should have `coordinator: true` per brainstorm session type (not enforced at load time, but convention).

---

## Example entry

```yaml
- role_id: backend
  display_name: Backend Developer Python
  skill_file: backend-developer-python.md
  coordinator: false
  capabilities:
    - python_backend
    - fastapi
    - database_migrations
    - api_implementation
  fsm_ownership:
    - implementation
  preferred_for:
    - python
    - api
    - database
    - migration
  brainstorm_also_for: []
  brainstorm_role: contributor
```

---

## LLM injection format

When forwarded to the Orchestrator LLM as `[AGENT REGISTRY]`, the registry is summarised as:

```
- {role_id} ({display_name}): {first 5 capabilities joined by ", "} | owns: {fsm_ownership joined by ", " or "cross-cutting"}
```

The raw YAML (`to_yaml_string()`) is also available for the agent-selector LLM call, which parses it directly.
