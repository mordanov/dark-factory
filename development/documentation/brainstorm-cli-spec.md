# Dark Factory — Brainstorm MCP CLI Integration
# Constitution + /speckit.specify Prompt

---

# PART 1 — CONSTITUTION

## Identity

This spec wires the existing `BrainstormCoordinator` in `agent-dispatcher`
to the real `brainstorm-mcp` server via its CLI tool (`brainstorm-messages`).

When `architecture_review` tickets trigger multi-agent brainstorm rounds,
agents already use `mcp__brainstorm__*` tools natively via their Claude
Code MCP config. The missing piece: the Dispatcher must READ what agents
wrote in the brainstorm session and deliver the transcript to the
Orchestrator for gate evaluation.

**Brainstorm is only for `architecture_review`.** All other FSM states
run a single agent with no brainstorm session. This is already defined
in the Capability Registry (`brainstorm_also_for` field).

No new service. Changes touch:
- `agent-dispatcher/src/services/brainstorm/cli_reader.py` (new)
- `agent-dispatcher/src/services/brainstorm_coordinator.py` (updated)
- `agent-dispatcher/src/core/config.py` (new env var)
- `orchestrator/src/services/llm/orchestrator_llm.py` (transcript injection)

---

## Core Principles

### 1. Read via CLI subprocess, not Python MCP SDK

The `brainstorm-messages` CLI tool already works (proven in `run-agents.sh`):
```bash
npx --prefix ~/.local/share/brainstorm-mcp brainstorm-messages "df-{ticket_id}"
```

Output is JSON array of messages. Use `asyncio.create_subprocess_exec`
to call it. No Python MCP SDK dependency needed.

### 2. Agents write, Dispatcher reads — never the other way

Agents write to brainstorm sessions via `mcp__brainstorm__send_message`
and related tools in their MCP config. The Dispatcher is read-only with
respect to brainstorm. It never writes messages to the session.

### 3. Empty session is not an error

If agents haven't posted any messages yet (e.g. they just started),
`cli_reader.read()` returns an empty list. This is a valid state.
The coordinator retries on the next polling cycle.

### 4. Transcript delivered in job payload to Orchestrator

After a brainstorm round completes (all agents for that round have
finished), the coordinator calls `cli_reader.read()`, builds a
`BrainstormTranscript`, and the reporter includes it in the
Orchestrator job trigger payload under `brainstorm_transcript`.

The Orchestrator LLM then evaluates the `architecture_consistency`
gate using the transcript.

### 5. Brainstorm session name from registry

Project name: `registry.brainstorm_project_name(ticket_id)` →
`"df-{ticket_id}"`. This ensures consistency between what agents join
and what the Dispatcher reads. Hardcoding is forbidden.

---

## CLI Reader Contract

`agent-dispatcher/src/services/brainstorm/cli_reader.py`

```python
@dataclass
class BrainstormMessage:
    author: str      # agent role_id or username
    content: str
    timestamp: str   # ISO8601 or raw from CLI

@dataclass
class BrainstormTranscript:
    project_name: str
    round_number: int
    max_rounds: int
    messages: list[BrainstormMessage]
    consensus: str   # "agreed" | "disagreed" | "inconclusive"

class BrainstormCLIReader:
    def __init__(self, npx_prefix: str, timeout_seconds: float = 30.0):
        self._prefix = npx_prefix      # e.g. ~/.local/share/brainstorm-mcp
        self._timeout = timeout_seconds

    async def read(self, project_name: str) -> list[BrainstormMessage]:
        """
        Call: npx --prefix {prefix} brainstorm-messages "{project_name}"
        Parse stdout as JSON array.
        Returns [] if session is empty or project doesn't exist.
        Raises UpstreamError on subprocess failure or timeout.
        """
        proc = await asyncio.create_subprocess_exec(
            "npx", "--prefix", self._prefix,
            "brainstorm-messages", project_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise UpstreamError(f"brainstorm-messages timed out after {self._timeout}s")

        if proc.returncode != 0:
            err = stderr.decode()[:300]
            if "no project" in err.lower() or "not found" in err.lower():
                return []   # project doesn't exist yet → empty session
            raise UpstreamError(f"brainstorm-messages failed: {err}")

        raw = stdout.decode().strip()
        if not raw or raw == "[]":
            return []

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise UpstreamError(f"brainstorm-messages bad JSON: {exc}") from exc

        return [
            BrainstormMessage(
                author=msg.get("author", msg.get("sender", "unknown")),
                content=msg.get("content", msg.get("message", "")),
                timestamp=msg.get("timestamp", msg.get("created_at", "")),
            )
            for msg in (data if isinstance(data, list) else [])
        ]
```

Note: `author` and `content` field names may vary based on
`brainstorm-mcp` version. The reader tries multiple field name aliases.
When adding the first integration test, inspect real CLI output and
update field names if needed.

---

## BrainstormCoordinator Update

`agent-dispatcher/src/services/brainstorm_coordinator.py`

After all agents for a round complete their `claude --print` run,
add a read step:

```python
# After round N agents finish:
reader = BrainstormCLIReader(
    npx_prefix=settings.brainstorm_npx_prefix,
    timeout_seconds=settings.brainstorm_cli_timeout_seconds,
)

project_name = self._registry.brainstorm_project_name(ticket.id)

try:
    messages = await reader.read(project_name)
    logger.info(
        "Brainstorm session '%s' round %d: %d messages",
        project_name, current_round, len(messages)
    )
except UpstreamError as exc:
    logger.warning("Could not read brainstorm session: %s", exc)
    messages = []

consensus = _derive_consensus(agent_results)

transcript = BrainstormTranscript(
    project_name=project_name,
    round_number=current_round,
    max_rounds=settings.brainstorm_max_rounds,
    messages=messages,
    consensus=consensus,
)
```

`_derive_consensus(agent_results: list[AgentResult]) -> str`:
```python
def _derive_consensus(results: list[AgentResult]) -> str:
    statuses = [r.brainstorm_consensus for r in results if r.brainstorm_consensus]
    if not statuses:
        return "inconclusive"
    if all(s == "agreed" for s in statuses):
        return "agreed"
    if any(s == "disagreed" for s in statuses):
        return "disagreed"
    return "inconclusive"
```

Return value from `run_brainstorm()` includes transcript:
```python
return {
    "concluded": True,
    "transcript": transcript,
    "rounds_completed": current_round,
    "agent_results": agent_results,
    "consensus": consensus,
}
```

---

## Orchestrator LLM Prompt Update

`orchestrator/src/services/llm/orchestrator_llm.py`

Already has `[BRAINSTORM TRANSCRIPT]` section specified in the
Brainstorm Integration constitution. Verify it is implemented.
If not, add after `[ADR LIST]`:

```python
transcript_raw = job_payload.get("brainstorm_transcript")
if transcript_raw:
    t = transcript_raw  # dict
    msg_lines = [
        f"  [{m['author']}]: {m['content']}"
        for m in t.get("messages", [])
    ]
    parts.append(
        f"[BRAINSTORM TRANSCRIPT]\n"
        f"Project: {t.get('project_name', '?')}\n"
        f"Round: {t.get('round_number', '?')} of {t.get('max_rounds', '?')}\n"
        f"Consensus: {t.get('consensus', 'inconclusive')}\n\n"
        + ("\n".join(msg_lines) or "(no messages)")
    )
elif ticket.fsm_status == "architecture_review":
    parts.append(
        "[BRAINSTORM TRANSCRIPT]\n"
        "No transcript yet. Agents have not completed brainstorm. "
        "Set action: WAIT unless brainstorm_round >= max_rounds."
    )
```

---

## New Environment Variables

Add to `agent-dispatcher/src/core/config.py`:

```python
# Path to local brainstorm-mcp node_modules prefix
# Default: ~/.local/share/brainstorm-mcp
brainstorm_npx_prefix: str = Field(
    default="~/.local/share/brainstorm-mcp",
    description="npx --prefix path for brainstorm-mcp CLI tools"
)
brainstorm_cli_timeout_seconds: float = Field(default=30.0)
```

Add to `infra/.env.example`:
```dotenv
# ─── Brainstorm MCP ──────────────────────────────────────────────────────
# Path to the brainstorm-mcp installation (where package.json lives)
# Run `which brainstorm-messages` or check your MCP config to find this.
BRAINSTORM_NPX_PREFIX=~/.local/share/brainstorm-mcp

# Timeout for reading brainstorm session messages via CLI (seconds)
BRAINSTORM_CLI_TIMEOUT_SECONDS=30
```

---

## Definition of Done

1. For an `architecture_review` ticket where two agents ran:
   `software-architect` and `security-architect` wrote messages
   → `BrainstormCLIReader.read("df-{ticket_id}")` returns those messages
2. Transcript appears in Orchestrator job trigger payload as
   `payload["brainstorm_transcript"]`
3. Orchestrator LLM prompt includes `[BRAINSTORM TRANSCRIPT]` section
4. Orchestrator can evaluate `architecture_consistency` gate from transcript
5. Empty session → `messages: []`, no error, coordinator continues
6. All unit tests pass; `BrainstormCLIReader` fully mocked in tests

---

## Principles That Must Never Be Violated

- **Dispatcher never writes to brainstorm sessions.** Read-only.
- **Empty session is valid state, not an error.**
- **Project name always from registry.** Never hardcoded.
- **`npx --prefix` path must be configurable** via env var.
- **Single-agent tickets skip brainstorm entirely.** No CLI call.

---

---

# PART 2 — /speckit.specify PROMPT

## Prompt (copy-paste into Claude Code)

```
/speckit.specify

Wire the existing BrainstormCoordinator in agent-dispatcher to the real
brainstorm-mcp CLI tool (brainstorm-messages) so that multi-agent
architecture_review sessions deliver actual transcript data to the
Orchestrator for gate evaluation.

Brainstorm is only for architecture_review tickets.
Single-agent tickets run standalone with no brainstorm session.
The CLI tool is called via asyncio subprocess — no Python MCP SDK.

Read ALL context files before generating the spec.

## Context files (read in this order)

@.specify/memory/constitution.md
@.specify/memory/service-map.md
@.specify/memory/project-map.md

Current code to understand and extend:
@../agent-dispatcher/src/services/brainstorm_coordinator.py
@../agent-dispatcher/src/services/reporter.py
@../agent-dispatcher/src/core/config.py
@../orchestrator/src/services/llm/orchestrator_llm.py
@../orchestrator/src/schemas/schemas.py
@../../development/run-agents.sh

Do not go above the ../../ directory level (monorepo root).

## What to specify

### 1. BrainstormCLIReader
   (`agent-dispatcher/src/services/brainstorm/cli_reader.py`)

Implement `BrainstormCLIReader` and `BrainstormTranscript` exactly as
specified in the constitution. Key points:

- Uses `asyncio.create_subprocess_exec` (not subprocess.run)
- `npx --prefix {settings.brainstorm_npx_prefix} brainstorm-messages {project_name}`
- Expand `~` in prefix path via `os.path.expanduser()`
- Parses stdout as JSON array
- Tries multiple field aliases: `author`/`sender`, `content`/`message`,
  `timestamp`/`created_at`
- Empty stdout or `[]` → return `[]` (not error)
- Non-zero exit with "not found" in stderr → return `[]`
- Non-zero exit otherwise → raise `UpstreamError`
- Timeout → kill proc, raise `UpstreamError`

Also create:
```python
def derive_consensus(agent_results: list[AgentResult]) -> str:
    """
    "agreed" if all non-null brainstorm_consensus == "agreed"
    "disagreed" if any == "disagreed"
    "inconclusive" otherwise (missing, mixed, or empty)
    """
```

### 2. BrainstormCoordinator update
   (`agent-dispatcher/src/services/brainstorm_coordinator.py`)

After ALL agents for a round finish:
1. Call `BrainstormCLIReader.read(project_name)` → list of messages
2. Call `derive_consensus(agent_results)` → str
3. Build `BrainstormTranscript` dataclass
4. Return transcript in `run_brainstorm()` result dict

On `UpstreamError` from CLI reader: log warning, set messages=[], continue.
Do NOT abort the brainstorm round on read failure.

Require registry as a constructor parameter to get `brainstorm_project_name`:
```python
class BrainstormCoordinator:
    def __init__(self, runner: AgentRunner, registry: CapabilityRegistry):
        self._runner = runner
        self._registry = registry
```

### 3. Reporter update
   (`agent-dispatcher/src/services/reporter.py`)

When a brainstorm result is available, serialize the transcript and
include in Orchestrator job trigger payload:

```python
payload: dict = {"registry_yaml": registry.to_yaml_string()}

if brainstorm_result and brainstorm_result.get("transcript"):
    t = brainstorm_result["transcript"]
    payload["brainstorm_transcript"] = {
        "project_name": t.project_name,
        "round_number": t.round_number,
        "max_rounds": t.max_rounds,
        "consensus": t.consensus,
        "messages": [
            {
                "author": m.author,
                "content": m.content,
                "timestamp": m.timestamp,
            }
            for m in t.messages
        ],
    }
```

### 4. Config additions
   (`agent-dispatcher/src/core/config.py`)

```python
brainstorm_npx_prefix: str = Field(
    default="~/.local/share/brainstorm-mcp"
)
brainstorm_cli_timeout_seconds: float = Field(default=30.0)
```

### 5. Orchestrator LLM prompt
   (`orchestrator/src/services/llm/orchestrator_llm.py`)

Check if `[BRAINSTORM TRANSCRIPT]` section already exists in
`_build_user_message()`. If it does, verify it:
- Renders all messages with author labels
- Shows consensus value
- Shows round N of max_rounds
- For `architecture_review` without transcript: shows WAIT hint

If missing, implement it exactly per the constitution.

### 6. Orchestrator schemas
   (`orchestrator/src/schemas/schemas.py`)

Add typed schemas for the transcript payload (for documentation
clarity — not strictly validated at runtime):

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

These are used for type hints in `orchestrator_llm.py` but not
enforced via FastAPI request validation.

### 7. .env.example update (`infra/.env.example`)

Add brainstorm section per constitution. Include comment explaining
how to find the npx prefix.

### 8. Tests

**`tests/unit/test_brainstorm_cli_reader.py`:**

All tests mock `asyncio.create_subprocess_exec`. Never call real npx.

```python
async def test_read_returns_messages_on_success():
    # Mock proc: returncode=0, stdout='[{"author":"backend","content":"I suggest...","timestamp":"..."}]'
    messages = await reader.read("df-test-ticket")
    assert len(messages) == 1
    assert messages[0].author == "backend"
    assert "suggest" in messages[0].content

async def test_read_returns_empty_on_empty_session():
    # Mock proc: returncode=0, stdout='[]'
    messages = await reader.read("df-test-ticket")
    assert messages == []

async def test_read_returns_empty_on_missing_project():
    # Mock proc: returncode=1, stderr="project not found"
    messages = await reader.read("df-nonexistent")
    assert messages == []

async def test_read_raises_on_other_error():
    # Mock proc: returncode=1, stderr="unexpected error"
    with pytest.raises(UpstreamError):
        await reader.read("df-test")

async def test_read_raises_on_timeout():
    # Mock proc.communicate() hangs → asyncio.wait_for raises TimeoutError
    with pytest.raises(UpstreamError, match="timed out"):
        await reader.read("df-test")

async def test_read_handles_sender_alias():
    # Mock stdout uses "sender" instead of "author"
    # '[{"sender":"frontend","message":"I propose..."}]'
    messages = await reader.read("df-test")
    assert messages[0].author == "frontend"

async def test_tilde_expanded_in_prefix():
    # Reader with prefix="~/.local/share/brainstorm-mcp"
    # Assert subprocess called with expanded path (no ~)
    # Use monkeypatch.setenv("HOME", "/home/testuser")
    ...
```

**`tests/unit/test_derive_consensus.py`:**

```python
def test_all_agreed():
    results = [
        AgentResult(brainstorm_consensus="agreed", ...),
        AgentResult(brainstorm_consensus="agreed", ...),
    ]
    assert derive_consensus(results) == "agreed"

def test_any_disagreed():
    results = [
        AgentResult(brainstorm_consensus="agreed", ...),
        AgentResult(brainstorm_consensus="disagreed", ...),
    ]
    assert derive_consensus(results) == "disagreed"

def test_null_consensus_is_inconclusive():
    results = [AgentResult(brainstorm_consensus=None, ...)]
    assert derive_consensus(results) == "inconclusive"

def test_empty_results():
    assert derive_consensus([]) == "inconclusive"

def test_mixed_with_null():
    results = [
        AgentResult(brainstorm_consensus="agreed", ...),
        AgentResult(brainstorm_consensus=None, ...),
    ]
    assert derive_consensus(results) == "inconclusive"
```

**`tests/unit/test_brainstorm_coordinator.py` (additions):**

```python
async def test_cli_reader_called_after_round():
    # Mock: BrainstormCLIReader.read returns 2 messages
    # Assert: run_brainstorm() result["transcript"].messages has 2 items

async def test_cli_reader_failure_does_not_abort():
    # Mock: BrainstormCLIReader.read raises UpstreamError
    # Assert: run_brainstorm() still returns result (empty messages)
    # Assert: transcript.consensus == "inconclusive"

async def test_transcript_in_return_value():
    result = await coordinator.run_brainstorm(ticket, briefing, db)
    assert "transcript" in result
    assert isinstance(result["transcript"], BrainstormTranscript)

async def test_project_name_from_registry():
    # Mock registry.brainstorm_project_name returns "df-ticket-xyz"
    # Assert: cli_reader.read called with "df-ticket-xyz"
```

**`tests/unit/test_orchestrator_llm.py` (additions):**

```python
def test_transcript_section_rendered():
    payload = {
        "brainstorm_transcript": {
            "project_name": "df-t1",
            "round_number": 1,
            "max_rounds": 3,
            "consensus": "inconclusive",
            "messages": [
                {"author": "software-architect",
                 "content": "Use event sourcing.", "timestamp": ""},
                {"author": "security-architect",
                 "content": "Agreed but add audit log.", "timestamp": ""},
            ],
        }
    }
    msg = _build_user_message(ticket, ev, None, [], {}, job_payload=payload)
    assert "[BRAINSTORM TRANSCRIPT]" in msg
    assert "software-architect" in msg
    assert "Use event sourcing" in msg
    assert "Round: 1 of 3" in msg
    assert "inconclusive" in msg

def test_no_transcript_for_arch_review_shows_wait_hint():
    ticket = make_ticket(fsm_status="architecture_review")
    msg = _build_user_message(ticket, ev, None, [], {}, job_payload={})
    assert "WAIT" in msg or "No transcript" in msg

def test_no_transcript_for_other_states_no_section():
    ticket = make_ticket(fsm_status="implementation")
    msg = _build_user_message(ticket, ev, None, [], {}, job_payload={})
    assert "[BRAINSTORM TRANSCRIPT]" not in msg
```

## Constraints (from constitution)

- Dispatcher is read-only to brainstorm: never call write/send tools
- Empty session → empty list, not error
- Project name always from `registry.brainstorm_project_name(ticket_id)`
- `~` expanded in npx prefix before subprocess call
- `asyncio.create_subprocess_exec` — not `subprocess.run` (blocking)
- No real npx call in any test
- Brainstorm only for `architecture_review` — single agents skip entirely

## Out of scope

- Writing messages to brainstorm from Dispatcher
- Brainstorm for non-architecture_review states
- Brainstorm session cleanup/archival
- Long-polling for real-time message delivery
```
