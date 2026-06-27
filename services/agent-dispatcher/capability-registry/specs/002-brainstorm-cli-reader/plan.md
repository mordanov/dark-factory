# Implementation Plan: Brainstorm CLI Reader

**Branch**: `002-brainstorm-cli-reader` | **Date**: 2026-06-27 | **Spec**: [spec.md](spec.md)

## Summary

Wire the existing `BrainstormCoordinator` in `agent-dispatcher` to the `brainstorm-messages` CLI tool so that multi-agent `architecture_review` sessions deliver actual transcript data to the Orchestrator for gate evaluation. The CLI is invoked via async subprocess after each brainstorm round completes. The Dispatcher is read-only with respect to brainstorm sessions. Single-agent tickets are unaffected.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: asyncio (stdlib), pydantic 2.10, structlog, existing FastAPI/SQLAlchemy stack  
**Storage**: N/A (no new persistence — transcript is passed through in-memory and delivered as payload)  
**Testing**: pytest + pytest-asyncio; all CLI calls mocked via `unittest.mock`  
**Target Platform**: Linux server (Docker container)  
**Project Type**: Internal service component (agent-dispatcher HTTP service)  
**Performance Goals**: CLI read must complete within configurable timeout (default 30s); adds negligible latency to brainstorm round completion  
**Constraints**: No blocking I/O — must use `asyncio.create_subprocess_exec`; no Python MCP SDK  
**Scale/Scope**: Called once per brainstorm round completion (≤3 rounds per ticket, triggered for `architecture_review` only)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| Registry is single source of truth for agent metadata | PASS | `brainstorm_project_name` derived from `registry.brainstorm_project_template` — no hardcoding |
| No new service created | PASS | Changes touch existing files only + one new file `cli_reader.py` |
| LLM selects agents, registry provides context | PASS | No change to agent selection logic |
| Credentials written before spawn | PASS | Unchanged |
| Registry loaded once at startup | PASS | Unchanged |
| Fallback is always defined | PASS | CLI read failure → empty transcript, brainstorm continues |
| Dispatcher is read-only to brainstorm | PASS | Constitution principle explicitly preserved |

No violations. Complexity tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/002-brainstorm-cli-reader/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code Changes

```text
# agent-dispatcher
services/agent-dispatcher/
├── src/
│   ├── services/
│   │   ├── brainstorm/
│   │   │   ├── __init__.py              [NEW]
│   │   │   └── cli_reader.py            [NEW] BrainstormCLIReader + BrainstormMessage + BrainstormTranscript + derive_consensus
│   │   ├── brainstorm_coordinator.py    [MODIFIED] accept registry, call cli_reader, return transcript
│   │   └── reporter.py                 [MODIFIED] include brainstorm_transcript in orchestrator payload
│   └── core/
│       └── config.py                   [MODIFIED] add brainstorm_npx_prefix + brainstorm_cli_timeout_seconds
└── tests/
    └── unit/
        ├── test_brainstorm_cli_reader.py    [NEW]
        ├── test_derive_consensus.py          [NEW]
        ├── test_brainstorm_coordinator.py    [MODIFIED — additions only]
        └── test_reporter.py                 [MODIFIED — additions only]

# orchestrator
services/orchestrator/
├── src/
│   ├── services/
│   │   └── llm/
│   │       └── orchestrator_llm.py     [MODIFIED] add [BRAINSTORM TRANSCRIPT] section to _build_user_message
│   └── schemas/
│       └── schemas.py                  [MODIFIED] add BrainstormMessagePayload + BrainstormTranscriptPayload
└── tests/
    └── unit/
        └── test_orchestrator_llm.py    [MODIFIED — additions only]

# infra
infra/
└── .env.example                        [MODIFIED] add BRAINSTORM_NPX_PREFIX + BRAINSTORM_CLI_TIMEOUT_SECONDS
```

---

## Phase 0: Research

### Finding 1: CLI Tool Output Format

**Decision**: The `brainstorm-messages` CLI returns a JSON array. Field names may vary by version. Reader tries aliases: `author`/`sender`, `content`/`message`, `timestamp`/`created_at`.

**Rationale**: Constitution specifies this explicitly. Current CLI behavior must be confirmed against real output when writing the first integration test; update field aliases then if needed.

**Alternatives considered**: Python MCP SDK — rejected (adds heavy dependency, CLI already proven in `run-agents.sh`).

### Finding 2: Subprocess Strategy

**Decision**: `asyncio.create_subprocess_exec` with `asyncio.wait_for` for timeout enforcement.

**Rationale**: Dispatcher is an async FastAPI service. `subprocess.run` would block the event loop. `create_subprocess_exec` avoids shell injection and is idiomatic for async Python.

**Alternatives considered**: `asyncio.create_subprocess_shell` — rejected (shell injection risk, no benefit).

### Finding 3: Tilde Expansion

**Decision**: `os.path.expanduser(self._prefix)` before passing to subprocess.

**Rationale**: `~` is not expanded by `execvp` on Linux. The default config value `~/.local/share/brainstorm-mcp` must be resolved to an absolute path before the syscall.

### Finding 4: BrainstormCoordinator Constructor Change

**Decision**: Add `registry: CapabilityRegistry` as a required constructor parameter alongside the existing `runner: AgentRunner`.

**Rationale**: Constitution spec and brainstorm-cli-spec.md both require `registry.brainstorm_project_name(ticket_id)` to derive the project name. The registry is already loaded at startup in `main.py` lifespan and available to the dispatcher.

**Impact on existing code**: `_run_brainstorm()` in `dispatcher_service.py` currently calls `BrainstormCoordinator(runner)` — must be updated to `BrainstormCoordinator(runner, registry)`.

**Impact on existing tests**: `test_brainstorm_coordinator.py` instantiates `BrainstormCoordinator(mock_runner)` in every test — all existing tests must pass a mock registry. The registry mock only needs to expose `brainstorm_project_name` returning a string.

### Finding 5: CapabilityRegistry Already Implements brainstorm_project_name

**Decision**: Confirm that `capability_registry.py` already has `brainstorm_project_name(ticket_id)` using `brainstorm_project_template` from `registry.yaml`. The template is `"df-{ticket_id}"`.

**Rationale**: Constitution schema shows `brainstorm_project_template: "df-{ticket_id}"`. The registry loader must already support this or the architecture_review brainstorm flow was never wired. Verified: `AgentContext.brainstorm_project_name` field exists in dispatcher schemas, confirming the registry already provides this.

### Finding 6: Reporter Signature Extension

**Decision**: Add `brainstorm_result: dict | None = None` parameter to `reporter.report_result()`. The `_trigger_orchestrator` helper extracts and serializes the transcript if present.

**Rationale**: Current `report_result` signature is `(ticket_id, project_id, result, registry=None)`. Adding `brainstorm_result` as a keyword argument is backward-compatible and matches the pattern already used by `registry`.

### Finding 7: Orchestrator LLM — No [BRAINSTORM TRANSCRIPT] Section Yet

**Decision**: `[BRAINSTORM TRANSCRIPT]` section does not exist in `_build_user_message()` (confirmed by reading `orchestrator_llm.py`). Must be added after `[ADR LIST]`.

**Rationale**: Current `_build_user_message` ends with `[DEPENDENCY STATUSES]`. The section insertion point is after `[ADR LIST]` per the brainstorm-cli-spec constitution.

---

## Phase 1: Design & Contracts

### Data Model

See [data-model.md](data-model.md) for entity definitions.

**Key data flow**:
```
CLI tool stdout (JSON array)
  → BrainstormCLIReader.read() → list[BrainstormMessage]
  → BrainstormCoordinator.run_brainstorm() → BrainstormTranscript (dataclass)
  → _run_brainstorm() in dispatcher_service.py → passes to reporter
  → Reporter._trigger_orchestrator() → serializes as dict → payload["brainstorm_transcript"]
  → Orchestrator job trigger HTTP POST
  → orchestrator_llm._build_user_message() → [BRAINSTORM TRANSCRIPT] section in LLM prompt
```

### Interface Contracts

See [contracts/brainstorm-transcript-payload.md](contracts/brainstorm-transcript-payload.md) for the Orchestrator job trigger payload extension.

### Detailed Implementation Notes

#### 1. `agent-dispatcher/src/services/brainstorm/__init__.py`
Empty file — creates the subpackage.

#### 2. `agent-dispatcher/src/services/brainstorm/cli_reader.py`

```python
@dataclass
class BrainstormMessage:
    author: str
    content: str
    timestamp: str

@dataclass
class BrainstormTranscript:
    project_name: str
    round_number: int
    max_rounds: int
    messages: list[BrainstormMessage]
    consensus: str   # "agreed" | "disagreed" | "inconclusive"

class BrainstormCLIReader:
    def __init__(self, npx_prefix: str, timeout_seconds: float = 30.0)
    async def read(self, project_name: str) -> list[BrainstormMessage]

def derive_consensus(results: list[AgentResult]) -> str
```

Key behaviours:
- `os.path.expanduser(npx_prefix)` before subprocess call
- `asyncio.create_subprocess_exec("npx", "--prefix", expanded_prefix, "brainstorm-messages", project_name, ...)`
- `asyncio.wait_for(proc.communicate(), timeout=self._timeout)`
- `TimeoutError` → `proc.kill()` → raise `UpstreamError("brainstorm-messages timed out after Xs")`
- non-zero exit + "not found"/"no project" in stderr → return `[]`
- non-zero exit otherwise → raise `UpstreamError`
- stdout empty or `"[]"` → return `[]`
- JSON parse failure → raise `UpstreamError`
- Field aliases: try `author` then `sender`; try `content` then `message`; try `timestamp` then `created_at`

`derive_consensus`:
- Filter `results` to those with non-None `brainstorm_consensus`
- Empty → `"inconclusive"`
- All `"agreed"` → `"agreed"`
- Any `"disagreed"` → `"disagreed"`
- Otherwise → `"inconclusive"`

#### 3. `agent-dispatcher/src/core/config.py` additions

```python
brainstorm_npx_prefix: str = Field(default="~/.local/share/brainstorm-mcp")
brainstorm_cli_timeout_seconds: float = Field(default=30.0)
```

#### 4. `agent-dispatcher/src/services/brainstorm_coordinator.py` changes

Constructor signature change:
```python
class BrainstormCoordinator:
    def __init__(self, runner: AgentRunner, registry: CapabilityRegistry) -> None:
        self._runner = runner
        self._registry = registry
```

After all agents for a round complete, add transcript assembly:
```python
from src.services.brainstorm.cli_reader import (
    BrainstormCLIReader, BrainstormTranscript, derive_consensus
)

project_name = self._registry.brainstorm_project_name(ticket.id)
reader = BrainstormCLIReader(
    npx_prefix=settings.brainstorm_npx_prefix,
    timeout_seconds=settings.brainstorm_cli_timeout_seconds,
)
try:
    messages = await reader.read(project_name)
except UpstreamError as exc:
    logger.warning("Could not read brainstorm session: %s", exc)
    messages = []

consensus_str = derive_consensus(agent_results)
transcript = BrainstormTranscript(
    project_name=project_name,
    round_number=round_num,
    max_rounds=max_rounds,
    messages=messages,
    consensus=consensus_str,
)
```

Return value includes transcript:
```python
return {
    "concluded": True,
    "consensus": consensus,         # existing field (early-exit string or None)
    "rounds_completed": round_num,
    "agent_results": agent_results,
    "transcript": transcript,       # NEW
}
```

**Important**: The CLI read happens once per round (after the round's agent loop, before deciding whether to break). The `transcript` in the return dict reflects the last-completed round's reading.

#### 5. `agent-dispatcher/src/services/dispatcher_service.py` changes

Update `_run_brainstorm` to pass registry to coordinator and transcript to reporter:
```python
coordinator = BrainstormCoordinator(runner, registry)
data = await coordinator.run_brainstorm(ticket, db, participants=participants)
result = aggregate_brainstorm(data)
await reporter.report_result(
    ticket_id=ticket.id,
    project_id=ticket.project_id,
    result=result,
    registry=registry,
    brainstorm_result=data,    # NEW
)
```

#### 6. `agent-dispatcher/src/services/reporter.py` changes

`report_result` signature:
```python
async def report_result(
    self,
    ticket_id: str,
    project_id: str,
    result: AgentResult,
    registry: object | None = None,
    brainstorm_result: dict | None = None,   # NEW
) -> None:
```

In `_trigger_orchestrator`, serialize transcript into payload:
```python
payload: dict = {"ticket_id": ticket_id, "project_id": project_id}
if registry is not None:
    payload["registry_yaml"] = registry.to_yaml_string()
if brainstorm_result and brainstorm_result.get("transcript"):
    t = brainstorm_result["transcript"]
    payload["brainstorm_transcript"] = {
        "project_name": t.project_name,
        "round_number": t.round_number,
        "max_rounds": t.max_rounds,
        "consensus": t.consensus,
        "messages": [
            {"author": m.author, "content": m.content, "timestamp": m.timestamp}
            for m in t.messages
        ],
    }
```

Also pass `brainstorm_result` through from `report_result` to `_trigger_orchestrator`:
```python
await self._trigger_orchestrator(
    settings.orchestrator_base_url,
    ticket_id, project_id, headers,
    registry=registry,
    brainstorm_result=brainstorm_result,   # NEW
)
```

#### 7. `orchestrator/src/services/llm/orchestrator_llm.py` changes

Add `[BRAINSTORM TRANSCRIPT]` section in `_build_user_message`, after `[ADR LIST]`, before `[DEPENDENCY STATUSES]`:

```python
# After ADR section, before dependency section:
transcript_raw = (job_payload or {}).get("brainstorm_transcript")
if transcript_raw:
    msg_lines = [
        f"  [{m['author']}]: {m['content']}"
        for m in transcript_raw.get("messages", [])
    ]
    parts.append(
        f"[BRAINSTORM TRANSCRIPT]\n"
        f"Project: {transcript_raw.get('project_name', '?')}\n"
        f"Round: {transcript_raw.get('round_number', '?')} of {transcript_raw.get('max_rounds', '?')}\n"
        f"Consensus: {transcript_raw.get('consensus', 'inconclusive')}\n\n"
        + ("\n".join(msg_lines) or "(no messages)")
    )
elif ticket.fsm_status == "architecture_review":
    parts.append(
        "[BRAINSTORM TRANSCRIPT]\n"
        "No transcript yet. Agents have not completed brainstorm. "
        "Set action: WAIT unless brainstorm_round >= max_rounds."
    )
# For other FSM states: no section added
```

#### 8. `orchestrator/src/schemas/schemas.py` additions

```python
class BrainstormMessagePayload(BaseModel):
    author: str
    content: str
    timestamp: str

class BrainstormTranscriptPayload(BaseModel):
    project_name: str
    round_number: int
    max_rounds: int
    consensus: str
    messages: list[BrainstormMessagePayload]
```

These are type-documentation schemas — not enforced by FastAPI validation on incoming requests.

#### 9. `infra/.env.example` additions

```dotenv
# ─── Brainstorm MCP ──────────────────────────────────────────────────────
# Path to the brainstorm-mcp installation (where package.json lives)
# Run `which brainstorm-messages` or check your MCP config to find this.
BRAINSTORM_NPX_PREFIX=~/.local/share/brainstorm-mcp

# Timeout for reading brainstorm session messages via CLI (seconds)
BRAINSTORM_CLI_TIMEOUT_SECONDS=30
```

---

### Test Plan

#### New: `tests/unit/test_brainstorm_cli_reader.py`

All tests mock `asyncio.create_subprocess_exec`. No real npx calls.

| Test | What it verifies |
|------|-----------------|
| `test_read_returns_messages_on_success` | returncode=0, JSON array → list[BrainstormMessage] with correct fields |
| `test_read_returns_empty_on_empty_stdout` | returncode=0, stdout=`[]` → empty list |
| `test_read_returns_empty_on_missing_project` | returncode=1, stderr="project not found" → empty list |
| `test_read_raises_on_other_error` | returncode=1, stderr="unexpected error" → UpstreamError |
| `test_read_raises_on_timeout` | communicate() hangs → UpstreamError matching "timed out" |
| `test_read_handles_sender_alias` | stdout uses `sender`/`message` keys → author/content mapped correctly |
| `test_tilde_expanded_in_prefix` | monkeypatch HOME; assert subprocess called with expanded path (no `~`) |

#### New: `tests/unit/test_derive_consensus.py`

| Test | Input | Expected |
|------|-------|----------|
| `test_all_agreed` | 2× `agreed` | `"agreed"` |
| `test_any_disagreed` | 1× `agreed`, 1× `disagreed` | `"disagreed"` |
| `test_null_consensus_is_inconclusive` | 1× `None` | `"inconclusive"` |
| `test_empty_results` | `[]` | `"inconclusive"` |
| `test_mixed_with_null` | 1× `agreed`, 1× `None` | `"inconclusive"` |

#### Additions to `tests/unit/test_brainstorm_coordinator.py`

All existing tests must be updated to pass a mock registry to `BrainstormCoordinator(mock_runner, mock_registry)`.

| New test | What it verifies |
|----------|-----------------|
| `test_cli_reader_called_after_round` | mock reader returns 2 messages → `result["transcript"].messages` has 2 items |
| `test_cli_reader_failure_does_not_abort` | reader raises UpstreamError → run still returns result with `messages=[]` |
| `test_transcript_in_return_value` | `run_brainstorm()` result has `"transcript"` key of type `BrainstormTranscript` |
| `test_project_name_from_registry` | registry.brainstorm_project_name returns `"df-ticket-xyz"` → reader.read called with that value |

#### Additions to `tests/unit/test_reporter.py`

| New test | What it verifies |
|----------|-----------------|
| `test_report_result_includes_transcript_in_payload` | brainstorm_result with transcript → payload["brainstorm_transcript"] present with correct structure |
| `test_report_result_no_transcript_when_none` | brainstorm_result=None → no `brainstorm_transcript` key in payload |
| `test_report_result_no_transcript_when_empty_messages` | transcript with messages=[] → payload still includes transcript (with empty messages list) |

#### Additions to `tests/unit/test_orchestrator_llm.py`

| New test | What it verifies |
|----------|-----------------|
| `test_transcript_section_rendered` | payload with transcript → prompt contains `[BRAINSTORM TRANSCRIPT]`, author labels, content, `Round: 1 of 3`, consensus |
| `test_no_transcript_for_arch_review_shows_wait_hint` | architecture_review ticket, no transcript → prompt contains "WAIT" or "No transcript" |
| `test_no_transcript_for_other_states_no_section` | implementation ticket, no transcript → no `[BRAINSTORM TRANSCRIPT]` in prompt |

---

## Implementation Order (for /speckit-tasks)

1. **Config additions** — `config.py` new fields (no dependencies)
2. **`brainstorm/cli_reader.py`** — new file, standalone (depends on config fields)
3. **`derive_consensus`** — in `cli_reader.py` or as a standalone function (no external deps)
4. **`BrainstormCoordinator` update** — constructor + transcript assembly (depends on cli_reader)
5. **`dispatcher_service.py` update** — pass registry to coordinator, pass brainstorm_result to reporter (depends on coordinator change)
6. **`reporter.py` update** — serialize transcript into payload (depends on coordinator return type)
7. **`orchestrator_llm.py` update** — add `[BRAINSTORM TRANSCRIPT]` section (independent of dispatcher changes)
8. **`orchestrator/schemas.py` additions** — payload schemas (independent)
9. **`.env.example` update** — documentation only (independent)
10. **Tests** — after each component is implemented

---

## Agent Context

<!-- SPECKIT START -->
Read: specs/002-brainstorm-cli-reader/plan.md
<!-- SPECKIT END -->
