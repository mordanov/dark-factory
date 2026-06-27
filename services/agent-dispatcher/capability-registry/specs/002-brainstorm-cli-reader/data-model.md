# Data Model: Brainstorm CLI Reader

## Entities

### BrainstormMessage (dataclass — agent-dispatcher)

Represents a single message posted by an agent in a brainstorm session.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `author` | `str` | CLI JSON `author` or `sender` | Agent role ID (e.g., `software-architect`) |
| `content` | `str` | CLI JSON `content` or `message` | The message text posted by the agent |
| `timestamp` | `str` | CLI JSON `timestamp` or `created_at` | ISO8601 or raw; may be empty string |

Field aliases are tried left-to-right. If neither alias is present, defaults to `""` for `content`/`timestamp` and `"unknown"` for `author`.

---

### BrainstormTranscript (dataclass — agent-dispatcher)

The assembled result of reading one brainstorm round's session.

| Field | Type | Notes |
|-------|------|-------|
| `project_name` | `str` | e.g., `"df-TKT-001"` — from `registry.brainstorm_project_name(ticket_id)` |
| `round_number` | `int` | Which round this transcript was read after |
| `max_rounds` | `int` | Max rounds from settings (context for the Orchestrator) |
| `messages` | `list[BrainstormMessage]` | Ordered as returned by CLI; may be empty |
| `consensus` | `str` | `"agreed"` \| `"disagreed"` \| `"inconclusive"` — derived from agent results |

---

### BrainstormMessagePayload (Pydantic BaseModel — orchestrator)

Typed representation of the per-message dict in the Orchestrator job trigger payload.

| Field | Type |
|-------|------|
| `author` | `str` |
| `content` | `str` |
| `timestamp` | `str` |

---

### BrainstormTranscriptPayload (Pydantic BaseModel — orchestrator)

Typed representation of the `brainstorm_transcript` key in the Orchestrator job trigger payload.

| Field | Type |
|-------|------|
| `project_name` | `str` |
| `round_number` | `int` |
| `max_rounds` | `int` |
| `consensus` | `str` |
| `messages` | `list[BrainstormMessagePayload]` |

These models are used for type hints in `orchestrator_llm.py` but are not enforced via FastAPI request validation.

---

## Consensus Derivation Rules

| Agent results | Derived consensus |
|---------------|------------------|
| All non-null `brainstorm_consensus` == `"agreed"` | `"agreed"` |
| Any non-null `brainstorm_consensus` == `"disagreed"` | `"disagreed"` |
| All null / empty list / mixed with null | `"inconclusive"` |

---

## Data Flow

```
brainstorm-messages CLI
  stdout: JSON array
    [{"author": "software-architect", "content": "...", "timestamp": "..."},
     {"sender": "security-architect", "message": "...", "created_at": "..."}]
       ↓ BrainstormCLIReader.read()
  list[BrainstormMessage]
       ↓ BrainstormCoordinator.run_brainstorm() + derive_consensus()
  BrainstormTranscript (dataclass)
       ↓ reporter.report_result(brainstorm_result={"transcript": ...})
       ↓ _trigger_orchestrator() serialization
  dict payload["brainstorm_transcript"]
    {"project_name": "df-TKT-001", "round_number": 1, "max_rounds": 3,
     "consensus": "inconclusive",
     "messages": [{"author": "software-architect", "content": "...", "timestamp": "..."}]}
       ↓ Orchestrator HTTP POST /api/v1/jobs/trigger
       ↓ orchestrator_llm._build_user_message()
  [BRAINSTORM TRANSCRIPT] section in LLM prompt
```

---

## State Transitions (Consensus)

```
agent_results list
  ├── empty or all consensus == None  →  "inconclusive"
  ├── all non-null == "agreed"        →  "agreed"
  ├── any non-null == "disagreed"     →  "disagreed"
  └── mix of "agreed" and None        →  "inconclusive"
```
