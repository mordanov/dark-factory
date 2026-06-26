# /speckit.specify — Agent Capability Registry + Dynamic Selection

## Prompt (copy-paste into Claude Code)

```
/speckit.specify

Implement the Agent Capability Registry and dynamic LLM-assisted agent
selection for Dark Factory. This replaces the hardcoded AGENT_FOR_STATE
dict in the Orchestrator FSM with capability-driven agent selection.

Changes touch: agent-dispatcher (registry loader, credentials writer,
registry delivery) and orchestrator (FSM engine, agent selector,
LLM prompt). No new service.

Read ALL context files before generating the spec.

## Context files (read in this order)

@.specify/memory/constitution.md
@.specify/memory/service-map.md
@.specify/memory/project-map.md

Current code to understand and modify:
@../orchestrator/src/services/fsm/engine.py
@../orchestrator/src/services/llm/orchestrator_llm.py
@../orchestrator/src/services/orchestrator_service.py
@../orchestrator/src/schemas/schemas.py
@../agent-dispatcher/src/services/dispatcher_service.py
@../agent-dispatcher/src/services/reporter.py
@../agent-dispatcher/src/core/config.py
@../agent-dispatcher/src/main.py
@../../development/agents/

Do not go above the ../../ directory level (monorepo root).

## What to specify

### 1. Registry file
   (`development/agents/registry.yaml`)

Create the full registry as specified in the constitution.
All 10 agents with exact role_ids matching run-agents.sh:
`project-administrator`, `product-manager`, `software-architect`,
`security-architect`, `backend`, `frontend`, `designer`,
`code-reviewer`, `autotester`, `devops`.

Include all fields: `role_id`, `display_name`, `skill_file`,
`coordinator`, `capabilities`, `fsm_ownership`, `brainstorm_role`,
plus `preferred_for` and `brainstorm_also_for` where applicable.

Top-level fields: `version: "1.0"` and
`brainstorm_project_template: "df-{ticket_id}"`.

### 2. CapabilityRegistry class
   (`agent-dispatcher/src/services/capability_registry.py`)

```python
from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass
class AgentCapability:
    role_id: str
    display_name: str
    skill_file: str
    coordinator: bool
    capabilities: list[str]
    fsm_ownership: list[str]
    preferred_for: list[str]           # keyword hints for LLM selection
    brainstorm_also_for: list[str]     # FSM states where agent joins brainstorm
    brainstorm_role: str               # coordinator | contributor

class CapabilityRegistry:
    def __init__(self, registry_path: str | Path):
        self._path = Path(registry_path)
        self._agents: list[AgentCapability] = []
        self._by_role: dict[str, AgentCapability] = {}
        self._by_state: dict[str, list[AgentCapability]] = {}
        self.brainstorm_project_template: str = "df-{ticket_id}"
        self._raw_yaml: str = ""

    def load(self) -> None:
        """Load and parse registry.yaml. Raises FileNotFoundError or ValueError."""
        raw = self._path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        self._raw_yaml = raw
        self.brainstorm_project_template = data.get(
            "brainstorm_project_template", "df-{ticket_id}"
        )
        self._agents = []
        for entry in data.get("agents", []):
            agent = AgentCapability(
                role_id=entry["role_id"],
                display_name=entry["display_name"],
                skill_file=entry["skill_file"],
                coordinator=entry.get("coordinator", False),
                capabilities=entry.get("capabilities", []),
                fsm_ownership=entry.get("fsm_ownership", []),
                preferred_for=entry.get("preferred_for", []),
                brainstorm_also_for=entry.get("brainstorm_also_for", []),
                brainstorm_role=entry.get("brainstorm_role", "contributor"),
            )
            self._agents.append(agent)
            self._by_role[agent.role_id] = agent
            for state in agent.fsm_ownership:
                self._by_state.setdefault(state, []).append(agent)

    def get_candidates_for_state(self, fsm_state: str) -> list[AgentCapability]:
        """Return agents that own this FSM state."""
        return self._by_state.get(fsm_state, [])

    def get_brainstorm_participants(self, fsm_state: str) -> list[AgentCapability]:
        """Return agents that participate in brainstorm for this FSM state."""
        result = list(self._by_state.get(fsm_state, []))
        for agent in self._agents:
            if fsm_state in agent.brainstorm_also_for and agent not in result:
                result.append(agent)
        return result

    def get_by_role_id(self, role_id: str) -> AgentCapability | None:
        return self._by_role.get(role_id)

    def all_role_ids(self) -> list[str]:
        return [a.role_id for a in self._agents]

    def to_yaml_string(self) -> str:
        """Return the raw YAML for injection into LLM prompts."""
        return self._raw_yaml

    def brainstorm_project_name(self, ticket_id: str) -> str:
        return self.brainstorm_project_template.format(ticket_id=ticket_id)
```

### 3. Config addition
   (`agent-dispatcher/src/core/config.py`)

Add:
```python
# Path to registry.yaml relative to AGENT_PROMPTS_DIR
# Default: registry.yaml in the same dir as skill files
agent_registry_path: str = Field(default="")

@property
def resolved_registry_path(self) -> str:
    if self.agent_registry_path:
        return self.agent_registry_path
    # Default: sibling of AGENT_PROMPTS_DIR
    from pathlib import Path
    return str(Path(self.agent_prompts_dir).parent / "registry.yaml")
```

### 4. Registry loading in lifespan
   (`agent-dispatcher/src/main.py`)

```python
from src.services.capability_registry import CapabilityRegistry

_registry: CapabilityRegistry | None = None

def get_registry() -> CapabilityRegistry:
    if _registry is None:
        raise RuntimeError("Registry not loaded")
    return _registry

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _registry
    _registry = CapabilityRegistry(settings.resolved_registry_path)
    _registry.load()
    logger.info(
        "Capability registry loaded: %d agents",
        len(_registry.all_role_ids())
    )
    worker = get_worker()
    await worker.start()
    yield
    await worker.stop()
```

Export `get_registry` from a dependencies module so other services
can access it via FastAPI `Depends(get_registry)`.

### 5. FSM engine changes
   (`orchestrator/src/services/fsm/engine.py`)

**Delete** the `AGENT_FOR_STATE` dict entirely.

**Change** `FSMEvaluation` dataclass:
```python
@dataclass
class FSMEvaluation:
    action: str
    from_state: str | None
    to_state: str | None
    candidate_agents: list[str]    # ← replaces assigned_agent: str | None
    blocked_reason: str | None
    gates_to_evaluate: list[str]
    generate_adr: bool
    context_distiller_trigger: bool
    errors: list[str]
```

**Change** `evaluate()` return value:
Instead of `assigned_agent=AGENT_FOR_STATE.get(to_state, "project-manager")`,
return `candidate_agents=[]` — the registry lookup happens in dispatcher,
not in the FSM engine. This keeps the FSM engine registry-agnostic (SRP).

The FSM engine's job: determine WHAT to do (which state, which gates).
The registry's job: determine WHO should do it.

**Remove** the `AGENT_FOR_STATE` import/reference from all callers.

### 6. Agent Selector
   (`orchestrator/src/services/fsm/agent_selector.py`)

New module. Makes a fast, focused LLM call to select from candidates.

```python
import json
import logging
from openai import AsyncOpenAI
from src.core.config import get_settings
from src.schemas.schemas import TmTicket

logger = logging.getLogger(__name__)
settings = get_settings()

_SYSTEM = (
    "You are selecting the best Dark Factory agent for a task. "
    "Return ONLY valid JSON: {\"selected\": \"<role_id>\"} "
    "The role_id MUST be from the candidates list. No other text."
)

async def select_agent(
    ticket: TmTicket,
    to_state: str,
    candidate_role_ids: list[str],
    registry_yaml: str,
    project_memory: str | None = None,
) -> str:
    """
    LLM-assisted agent selection.
    Always returns a valid role_id from candidate_role_ids.
    Falls back to candidate_role_ids[0] on any failure.
    """
    if not candidate_role_ids:
        return "product-manager"   # safe default

    if len(candidate_role_ids) == 1:
        return candidate_role_ids[0]   # no LLM needed

    # Build candidate summary from registry YAML
    import yaml
    registry = yaml.safe_load(registry_yaml)
    candidate_summaries = []
    for entry in registry.get("agents", []):
        if entry["role_id"] in candidate_role_ids:
            caps = ", ".join(entry.get("capabilities", []))
            hints = ", ".join(entry.get("preferred_for", []))
            candidate_summaries.append(
                f"- {entry['role_id']}: {entry['display_name']}\n"
                f"  capabilities: {caps}\n"
                f"  preferred when ticket mentions: {hints}"
            )

    user_msg = (
        f"[TICKET]\n"
        f"title: {ticket.title}\n"
        f"type: {ticket.ticket_type or 'unknown'}\n"
        f"description: {(ticket.description or '')[:400]}\n\n"
        f"[TARGET FSM STATE]\n{to_state}\n\n"
        f"[CANDIDATES]\n" + "\n".join(candidate_summaries)
    )
    if project_memory:
        user_msg += f"\n\n[PROJECT CONTEXT]\n{project_memory[:300]}"

    try:
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=10.0,
        )
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=30,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        selected = data.get("selected", "")
        if selected in candidate_role_ids:
            return selected
        logger.warning("LLM selected unknown role '%s', falling back", selected)
    except Exception as exc:
        logger.warning("Agent selector LLM failed: %s, falling back", exc)

    return candidate_role_ids[0]
```

### 7. Orchestrator LLM prompt update
   (`orchestrator/src/services/llm/orchestrator_llm.py`)

In `_build_user_message()`, add `[AGENT REGISTRY]` section after
`[ADR LIST]` when `registry_yaml` is available in `job_payload`:

```python
registry_yaml = job_payload.get("registry_yaml", "")
if registry_yaml:
    parts.append(
        "[AGENT REGISTRY]\n"
        "Available agents (role_id: capabilities):\n"
        + _summarize_registry(registry_yaml)
    )
```

```python
def _summarize_registry(registry_yaml: str) -> str:
    """Compact summary for LLM context."""
    import yaml
    try:
        data = yaml.safe_load(registry_yaml)
        lines = []
        for a in data.get("agents", []):
            caps = ", ".join(a.get("capabilities", [])[:5])  # first 5 caps
            owned = ", ".join(a.get("fsm_ownership", [])) or "cross-cutting"
            lines.append(f"- {a['role_id']} ({a['display_name']}): {caps} | owns: {owned}")
        return "\n".join(lines)
    except Exception:
        return registry_yaml[:500]
```

Update `call_orchestrator_llm()` signature:
```python
async def call_orchestrator_llm(
    ticket: TmTicket,
    fsm_eval: FSMEvaluation,
    project_memory: ProjectMemoryResponse | None,
    adrs: list[AdrSummary],
    dependency_statuses: dict[str, str],
    job_payload: dict,                  # ← already present, ensure used
) -> OrchestratorDecision:
```

Also: the orchestrator system prompt must instruct the LLM that
`assigned_agent` in its output MUST be a `role_id` from the registry.
Add to `_SYSTEM_PROMPT`:
```
- assigned_agent MUST be a role_id from the [AGENT REGISTRY] section.
  If registry is absent, use one of: product-manager, software-architect,
  backend, frontend, code-reviewer, security-architect, autotester, devops.
```

### 8. Orchestrator service update
   (`orchestrator/src/services/orchestrator_service.py`)

After calling `call_orchestrator_llm()`, validate `assigned_agent`:

```python
from src.services.fsm.agent_selector import select_agent

# After LLM call returns decision:
assigned = decision.decision.assigned_agent

# Validate against known roles (passed in job payload)
registry_yaml = job.payload.get("registry_yaml", "")
if registry_yaml and assigned:
    import yaml
    valid_roles = [
        a["role_id"]
        for a in yaml.safe_load(registry_yaml).get("agents", [])
    ]
    if assigned not in valid_roles:
        logger.warning(
            "LLM assigned unknown role '%s', running selector", assigned
        )
        # Run agent_selector as fallback using candidate_agents from FSM eval
        assigned = await select_agent(
            ticket=ticket,
            to_state=fsm_eval.to_state or "",
            candidate_role_ids=fsm_eval.candidate_agents,
            registry_yaml=registry_yaml,
            project_memory=memory.content if memory else None,
        )
        # Patch decision
        decision.decision.assigned_agent = assigned
```

### 9. Reporter update — include registry
   (`agent-dispatcher/src/services/reporter.py`)

```python
async def report_result(
    ticket_id: str,
    project_id: str,
    result: AgentResult,
    registry: CapabilityRegistry,         # ← new param
) -> None:

    payload: dict = {}
    payload["registry_yaml"] = registry.to_yaml_string()

    if brainstorm_result:
        payload["brainstorm_transcript"] = dataclasses.asdict(
            brainstorm_result["transcript"]
        )

    await orchestrator_client.post(
        f"{settings.orchestrator_base_url}/api/v1/jobs/trigger",
        json={
            "ticket_id": ticket_id,
            "project_id": project_id,
            "priority": 5,
            "payload": payload,
        },
        headers=await get_kc_client().async_auth_headers(),
    )
```

All call sites of `report_result()` pass the registry.

### 10. Credentials.json writer
   (`agent-dispatcher/src/services/dispatcher_service.py`)

Add `_write_credentials()` method called before every agent spawn:

```python
async def _write_credentials(self, role_id: str) -> None:
    """Write credentials.json to development/{role_id}/ before spawn."""
    from pathlib import Path
    import json

    # Get TM token via service client
    tm_token = await self._tm.get_service_token()

    creds = {
        "host": str(settings.ticket_manager_base_url),
        "token": tm_token,
        "role": role_id,
    }

    creds_dir = Path(settings.agent_prompts_dir).parent / role_id
    creds_dir.mkdir(parents=True, exist_ok=True)
    creds_path = creds_dir / "credentials.json"
    creds_path.write_text(json.dumps(creds, indent=2))
    logger.info("Credentials written: %s", creds_path)
```

Call `_write_credentials(agent_id)` in `process_ticket()` immediately
before `runner.run()`.

`TicketManagerClient` needs a new method `get_service_token() -> str`
that returns the current access token (already has `_token` internally).

### 11. .gitignore update

Add at monorepo root `.gitignore`:
```gitignore
# Agent credentials (written at runtime by agent-dispatcher)
development/**/credentials.json
```

### 12. Tests

**`tests/unit/test_capability_registry.py`:**

```python
SAMPLE_YAML = """
version: "1.0"
brainstorm_project_template: "df-{ticket_id}"
agents:
  - role_id: backend
    display_name: Backend Developer
    skill_file: backend-developer-python.md
    coordinator: false
    capabilities: [python_backend, fastapi]
    fsm_ownership: [implementation]
    preferred_for: [python, api]
    brainstorm_also_for: []
    brainstorm_role: contributor
  - role_id: frontend
    display_name: Frontend Developer
    skill_file: frontend-developer-react.md
    coordinator: false
    capabilities: [react, typescript]
    fsm_ownership: [implementation]
    preferred_for: [react, ui]
    brainstorm_also_for: []
    brainstorm_role: contributor
  - role_id: software-architect
    display_name: Software Architect
    skill_file: software-architect.md
    coordinator: false
    capabilities: [system_design, adr_generation]
    fsm_ownership: [architecture_review]
    preferred_for: []
    brainstorm_also_for: []
    brainstorm_role: contributor
  - role_id: security-architect
    display_name: Security Architect
    skill_file: security-architect.md
    coordinator: false
    capabilities: [security_review]
    fsm_ownership: [security_review]
    preferred_for: []
    brainstorm_also_for: [architecture_review]
    brainstorm_role: contributor
"""

def test_load_succeeds(tmp_path):
    f = tmp_path / "registry.yaml"
    f.write_text(SAMPLE_YAML)
    reg = CapabilityRegistry(f)
    reg.load()
    assert len(reg.all_role_ids()) == 4

def test_get_candidates_for_implementation():
    reg = _loaded(SAMPLE_YAML)
    candidates = reg.get_candidates_for_state("implementation")
    assert {a.role_id for a in candidates} == {"backend", "frontend"}

def test_get_candidates_for_unknown_state():
    reg = _loaded(SAMPLE_YAML)
    assert reg.get_candidates_for_state("nonexistent") == []

def test_get_brainstorm_participants_includes_also_for():
    reg = _loaded(SAMPLE_YAML)
    participants = reg.get_brainstorm_participants("architecture_review")
    role_ids = {a.role_id for a in participants}
    assert "software-architect" in role_ids
    assert "security-architect" in role_ids   # via brainstorm_also_for

def test_get_by_role_id_found():
    reg = _loaded(SAMPLE_YAML)
    agent = reg.get_by_role_id("backend")
    assert agent.display_name == "Backend Developer"

def test_get_by_role_id_not_found():
    reg = _loaded(SAMPLE_YAML)
    assert reg.get_by_role_id("unknown") is None

def test_brainstorm_project_name():
    reg = _loaded(SAMPLE_YAML)
    assert reg.brainstorm_project_name("abc123") == "df-abc123"

def test_to_yaml_string_is_valid_yaml():
    reg = _loaded(SAMPLE_YAML)
    import yaml
    parsed = yaml.safe_load(reg.to_yaml_string())
    assert "agents" in parsed

def test_missing_file_raises():
    reg = CapabilityRegistry("/nonexistent/registry.yaml")
    with pytest.raises(FileNotFoundError):
        reg.load()
```

**`tests/unit/test_agent_selector.py`:**

```python
async def test_single_candidate_no_llm_call():
    result = await select_agent(ticket, "code_review", ["code-reviewer"], yaml, None)
    assert result == "code-reviewer"
    # LLM must NOT be called — verify with mock

async def test_empty_candidates_returns_default():
    result = await select_agent(ticket, "unknown", [], yaml, None)
    assert result == "product-manager"

async def test_llm_selects_backend_for_python_ticket():
    # Mock LLM returns {"selected": "backend"}
    # Ticket title: "Implement PostgreSQL migration for users table"
    result = await select_agent(python_ticket, "implementation",
                                ["backend", "frontend"], yaml, None)
    assert result == "backend"

async def test_llm_selects_frontend_for_react_ticket():
    # Mock LLM returns {"selected": "frontend"}
    # Ticket title: "Add React component for user profile"
    result = await select_agent(react_ticket, "implementation",
                                ["backend", "frontend"], yaml, None)
    assert result == "frontend"

async def test_invalid_llm_response_falls_back():
    # Mock LLM returns {"selected": "nonexistent-agent"}
    result = await select_agent(ticket, "implementation",
                                ["backend", "frontend"], yaml, None)
    assert result == "backend"   # first candidate

async def test_llm_timeout_falls_back():
    # Mock LLM raises asyncio.TimeoutError
    result = await select_agent(ticket, "implementation",
                                ["backend", "frontend"], yaml, None)
    assert result == "backend"

async def test_llm_api_error_falls_back():
    # Mock LLM raises openai.APIError
    result = await select_agent(ticket, "implementation",
                                ["backend", "frontend"], yaml, None)
    assert result in ["backend", "frontend"]
```

**`tests/unit/test_fsm_engine.py` — additions:**

```python
def test_evaluate_returns_candidate_agents_not_assigned():
    ticket = make_ticket(fsm_status="triage", ticket_type="feature")
    result = evaluate(ticket, {})
    assert hasattr(result, "candidate_agents")
    assert not hasattr(result, "assigned_agent")

def test_implementation_has_multiple_candidates():
    ticket = make_ticket(fsm_status="specification", ticket_type="feature")
    # Patch registry to have backend + frontend for implementation
    result = evaluate(ticket, {})
    # candidate_agents should not be empty for implementation transition
    assert isinstance(result.candidate_agents, list)

def test_agent_for_state_does_not_exist():
    import orchestrator.src.services.fsm.engine as engine_module
    assert not hasattr(engine_module, "AGENT_FOR_STATE")
```

## Constraints (from constitution)

- `AGENT_FOR_STATE` dict deleted — no hardcoded role strings
- Registry loaded once at startup — no per-request file I/O
- `select_agent()` never raises — always returns a role_id string
- `assigned_agent` in orchestrator output validated against registry
- `credentials.json` is gitignored
- role_ids use hyphenated format matching run-agents.sh
- Agent selector timeout: 10 seconds maximum

## Out of scope

- GUI for managing the registry
- Per-project capability overrides (uses project-memory overrides already in place)
- Agent load balancing (future)
- Capability versioning
```
