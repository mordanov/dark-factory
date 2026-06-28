# Tasks: Brainstorm CLI Reader

**Input**: Design documents from `specs/002-brainstorm-cli-reader/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Included — success criteria SC-006 explicitly requires unit test coverage with 100% mocked CLI calls.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: User story label (US1–US4)

---

## Phase 1: Setup

**Purpose**: Create the new `brainstorm` subpackage so imports resolve before any code is written.

- [x] T001 Create `services/agent-dispatcher/src/services/brainstorm/__init__.py` (empty file — establishes subpackage)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config additions required by all subsequent phases.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Add `brainstorm_npx_prefix: str = Field(default="~/.local/share/brainstorm-mcp")` and `brainstorm_cli_timeout_seconds: float = Field(default=30.0)` to the `Settings` class in `services/agent-dispatcher/src/core/config.py`

**Checkpoint**: Config fields available — user story implementation can begin.

---

## Phase 3: User Story 1 — Architecture Review Delivers Transcript (Priority: P1) 🎯 MVP

**Goal**: After a multi-agent architecture_review round completes, the Orchestrator job trigger payload contains a `brainstorm_transcript` field with all agent messages.

**Independent Test**: Trigger `run_brainstorm()` with a mock cli_reader returning 2 messages; assert `reporter._trigger_orchestrator` receives a payload with `payload["brainstorm_transcript"]["messages"]` of length 2.

### Implementation

- [x] T003 [P] [US1] Define `BrainstormMessage` and `BrainstormTranscript` dataclasses (with `author`, `content`, `timestamp` and `project_name`, `round_number`, `max_rounds`, `messages`, `consensus` fields respectively) in `services/agent-dispatcher/src/services/brainstorm/cli_reader.py`
- [x] T004 [P] [US1] Implement `derive_consensus(results: list[AgentResult]) -> str` — returns `"agreed"` if all non-null consensus == agreed, `"disagreed"` if any == disagreed, `"inconclusive"` otherwise — in `services/agent-dispatcher/src/services/brainstorm/cli_reader.py`
- [x] T005 [US1] Implement `BrainstormCLIReader` class: `__init__(npx_prefix, timeout_seconds=30.0)` and `async read(project_name) -> list[BrainstormMessage]` — use `os.path.expanduser()` on prefix, call `asyncio.create_subprocess_exec("npx", "--prefix", expanded_prefix, "brainstorm-messages", project_name)`, wrap `proc.communicate()` in `asyncio.wait_for`, parse stdout as JSON array, map field aliases (`author`/`sender`, `content`/`message`, `timestamp`/`created_at`) — in `services/agent-dispatcher/src/services/brainstorm/cli_reader.py` (depends on T003)
- [x] T006 [US1] Update `BrainstormCoordinator.__init__` to `(self, runner: AgentRunner, registry: CapabilityRegistry)` storing `self._registry = registry`, then after all agents for a round complete in `run_brainstorm()`: call `self._registry.brainstorm_project_name(ticket.id)`, instantiate `BrainstormCLIReader` from settings, call `await reader.read(project_name)` wrapped in try/except UpstreamError (log warning, set `messages=[]`), call `derive_consensus(agent_results)`, build `BrainstormTranscript`, add `"transcript": transcript` to the return dict — in `services/agent-dispatcher/src/services/brainstorm_coordinator.py` (depends on T002, T005)
- [x] T007 [US1] Update `_run_brainstorm()` in `services/agent-dispatcher/src/services/dispatcher_service.py` to construct `BrainstormCoordinator(runner, registry)` (instead of `BrainstormCoordinator(runner)`) and pass `brainstorm_result=data` to `reporter.report_result()` (depends on T006)
- [x] T008 [US1] Update `Reporter.report_result()` signature to add `brainstorm_result: dict | None = None` and update `_trigger_orchestrator()` to accept and forward it; in `_trigger_orchestrator()` serialize `brainstorm_result["transcript"]` into `payload["brainstorm_transcript"]` as `{project_name, round_number, max_rounds, consensus, messages: [{author, content, timestamp}]}` when transcript is present — in `services/agent-dispatcher/src/services/reporter.py` (depends on T006)

### Tests

- [x] T009 [P] [US1] Update all existing `BrainstormCoordinator` tests in `services/agent-dispatcher/tests/unit/test_brainstorm_coordinator.py` to pass a mock registry (`MagicMock()` with `brainstorm_project_name.return_value = "df-TKT-BS-TEST"`) as the second constructor argument; add `test_cli_reader_called_after_round` (mock reader returns 2 messages → `result["transcript"].messages` has 2 items), `test_transcript_in_return_value` (`result["transcript"]` is a `BrainstormTranscript`), `test_project_name_from_registry` (reader.read called with `"df-TKT-BS-TEST"`)
- [x] T010 [P] [US1] Write `test_read_returns_messages_on_success` (returncode=0, stdout JSON with `author`/`content`/`timestamp` → list of BrainstormMessage with correct fields) and `test_read_handles_sender_alias` (stdout uses `sender`/`message` keys → author/content mapped correctly) in `services/agent-dispatcher/tests/unit/test_brainstorm_cli_reader.py` — mock `asyncio.create_subprocess_exec` throughout
- [x] T011 [P] [US1] Write `test_all_agreed`, `test_any_disagreed`, `test_null_consensus_is_inconclusive`, `test_empty_results`, `test_mixed_with_null` in `services/agent-dispatcher/tests/unit/test_derive_consensus.py`
- [x] T012 [P] [US1] Add `test_report_result_includes_transcript_in_payload` (brainstorm_result with transcript → `payload["brainstorm_transcript"]` present, all fields correct including `messages` list) to `services/agent-dispatcher/tests/unit/test_reporter.py`

**Checkpoint**: User Story 1 fully functional — transcript flows from CLI through coordinator, reporter, to Orchestrator payload.

---

## Phase 4: User Story 2 — Empty or Missing Session Does Not Block Processing (Priority: P2)

**Goal**: Empty stdout, missing project, timeout, and CLI errors all result in `messages=[]` and continued processing — never in a hard failure.

**Independent Test**: Trigger `BrainstormCLIReader.read()` with a mocked subprocess returning returncode=1 with stderr "project not found"; assert empty list returned and no exception raised. Then mock coordinator with UpstreamError from reader; assert `run_brainstorm()` returns without raising.

### Tests

- [x] T013 [P] [US2] Write `test_read_returns_empty_on_empty_stdout` (returncode=0, stdout=`[]`), `test_read_returns_empty_on_missing_project` (returncode=1, stderr="project not found"), `test_read_raises_on_other_error` (returncode=1, stderr="unexpected error" → UpstreamError), `test_read_raises_on_timeout` (communicate() hangs → UpstreamError matching "timed out"), `test_tilde_expanded_in_prefix` (monkeypatch HOME; assert subprocess called with expanded path, no `~`) in `services/agent-dispatcher/tests/unit/test_brainstorm_cli_reader.py`
- [x] T014 [P] [US2] Add `test_cli_reader_failure_does_not_abort` (mock BrainstormCLIReader.read raises UpstreamError → `run_brainstorm()` still returns result dict with `transcript.messages == []` and `transcript.consensus == "inconclusive"`) to `services/agent-dispatcher/tests/unit/test_brainstorm_coordinator.py`
- [x] T015 [P] [US2] Add `test_report_result_no_transcript_when_none` (brainstorm_result=None → no `brainstorm_transcript` key in trigger payload) and `test_report_result_empty_messages_list_included` (transcript with `messages=[]` → payload includes `brainstorm_transcript` with `messages: []`) to `services/agent-dispatcher/tests/unit/test_reporter.py`

**Checkpoint**: All empty/error resilience paths verified — empty session never blocks brainstorm round completion.

---

## Phase 5: User Story 3 — Single-Agent Tickets Skip Brainstorm Entirely (Priority: P3)

**Goal**: Non-architecture_review dispatches call `reporter.report_result()` without `brainstorm_result`; the Orchestrator payload has no `brainstorm_transcript` key.

**Independent Test**: Inspect all `reporter.report_result()` call sites in `dispatcher_service.py` that are not in `_run_brainstorm()`; confirm none pass `brainstorm_result`. Run the reporter test showing no transcript in payload.

### Implementation

- [x] T016 [US3] Review all `reporter.report_result()` call sites in `services/agent-dispatcher/src/services/dispatcher_service.py` (there are 5 total); confirm the non-brainstorm calls do not pass `brainstorm_result` (they use the new keyword arg's default `None`). If any call explicitly passes it, remove. No new code needed if defaults are correct — this is a verification + sign-off task.

### Tests

- [x] T017 [P] [US3] Add `test_no_brainstorm_transcript_for_non_architecture_review` — simulate a regular (non-brainstorm) `report_result()` call without `brainstorm_result`; assert the Orchestrator trigger payload has no `brainstorm_transcript` key — in `services/agent-dispatcher/tests/unit/test_reporter.py`

**Checkpoint**: Single-agent path confirmed clean — no transcript leaks into non-architecture_review payloads.

---

## Phase 6: User Story 4 — Orchestrator LLM Evaluates Gate Using Transcript (Priority: P4)

**Goal**: The Orchestrator decision prompt includes the full `[BRAINSTORM TRANSCRIPT]` section when a transcript is present; includes a WAIT hint for architecture_review without transcript; omits the section for other states.

**Independent Test**: Call `_build_user_message()` with a payload containing a transcript dict; assert prompt contains `[BRAINSTORM TRANSCRIPT]`, both agent author labels, message content, `Round: 1 of 3`, and consensus value.

### Implementation

- [x] T018 [P] [US4] Add `BrainstormMessagePayload(BaseModel)` with fields `author: str`, `content: str`, `timestamp: str` and `BrainstormTranscriptPayload(BaseModel)` with fields `project_name: str`, `round_number: int`, `max_rounds: int`, `consensus: str`, `messages: list[BrainstormMessagePayload]` to `services/orchestrator/src/schemas/schemas.py`
- [x] T019 [US4] Insert `[BRAINSTORM TRANSCRIPT]` section into `_build_user_message()` in `services/orchestrator/src/services/llm/orchestrator_llm.py`: after `[ADR LIST]`, before `[DEPENDENCY STATUSES]` — if `brainstorm_transcript` in job_payload: render project name, round N of max_rounds, consensus, and all agent messages as `  [author]: content`; elif `ticket.fsm_status == "architecture_review"`: render WAIT hint; else: no section (depends on T018)

### Tests

- [x] T020 [P] [US4] Add `test_transcript_section_rendered` (payload with 2-message transcript → prompt contains `[BRAINSTORM TRANSCRIPT]`, both author names, message content, `Round: 1 of 3`, `inconclusive`), `test_no_transcript_for_arch_review_shows_wait_hint` (architecture_review ticket, no transcript → prompt contains "WAIT" or "No transcript"), `test_no_transcript_for_other_states_no_section` (implementation ticket, no transcript → no `[BRAINSTORM TRANSCRIPT]` in prompt) to `services/orchestrator/tests/unit/test_orchestrator_llm.py`

**Checkpoint**: Orchestrator LLM receives and uses transcript — gate evaluation can proceed with full brainstorm context.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T021 [P] Add brainstorm MCP section to `infra/.env.example`: `BRAINSTORM_NPX_PREFIX=~/.local/share/brainstorm-mcp` with comment "Path to the brainstorm-mcp installation; run \`which brainstorm-messages\` or check your MCP config to find this" and `BRAINSTORM_CLI_TIMEOUT_SECONDS=30` with comment "Timeout for reading brainstorm session messages via CLI (seconds)"

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS** all user stories
- **US1 (Phase 3)**: Depends on Phase 2 completion
- **US2 (Phase 4)**: Depends on T005 (cli_reader) and T006 (coordinator) from Phase 3
- **US3 (Phase 5)**: Depends on T008 (reporter signature) from Phase 3
- **US4 (Phase 6)**: Independent of Phases 3–5 (different service)
- **Polish (Phase 7)**: Independent — can run any time after Phase 2

### Within Phase 3 (US1)

```
T003 (dataclasses)  ──┐
T004 (derive_consensus) ─┤
                        ├── T005 (CLIReader) ── T006 (coordinator) ── T007 (dispatcher_service)
                                                                    └── T008 (reporter)
```

Tests T009–T012 can all start after their respective implementation tasks (T006, T005, T004, T008).

### Parallel Opportunities

- T003 and T004 can run in parallel (different functions in same file)
- T009, T010, T011, T012 can all run in parallel (different test files)
- T013, T014, T015 can all run in parallel (different test files)
- T018 and T020 can run in parallel
- T021 is always parallel (infra file, no code deps)
- Phase 4 (US2 tests) and Phase 6 (US4) can run in parallel once Phase 3 is complete

---

## Parallel Example: User Story 1 Tests

```bash
# After T005, T006, T008 complete:
Task: "T009 — coordinator tests + registry mock updates"
Task: "T010 — cli_reader success tests"
Task: "T011 — derive_consensus tests"
Task: "T012 — reporter transcript payload test"
# All four can run simultaneously
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Create `__init__.py`
2. Complete Phase 2: Config fields
3. Complete Phase 3: US1 — end-to-end transcript delivery
4. **STOP and VALIDATE**: Confirm `result["transcript"]` flows through to Orchestrator payload
5. Run test suite: `pytest services/agent-dispatcher/tests/unit/test_brainstorm_cli_reader.py services/agent-dispatcher/tests/unit/test_derive_consensus.py services/agent-dispatcher/tests/unit/test_brainstorm_coordinator.py`

### Incremental Delivery

1. Setup + Foundational → T001–T002
2. US1 core + tests → T003–T012 (transcript delivery proven)
3. US2 resilience tests → T013–T015 (error paths verified)
4. US3 verification → T016–T017 (single-agent clean)
5. US4 orchestrator → T018–T020 (LLM uses transcript)
6. Polish → T021

### Parallel Team Strategy

With two developers:
- Developer A: Phases 3 + 4 (agent-dispatcher changes: cli_reader, coordinator, reporter, all dispatcher tests)
- Developer B: Phase 6 (orchestrator changes: orchestrator_llm, schemas, orchestrator tests)
- Both can proceed after Phase 2 completes

---

## Notes

- [P] tasks touch different files with no cross-task dependency
- All CLI calls must be mocked in every test — no real `npx` invocations
- `BrainstormCoordinator(runner)` call sites in existing tests must all be updated to `BrainstormCoordinator(runner, mock_registry)` in T009 — this is the only breaking change
- T016 is intentionally a low-effort verification task; if all existing call sites already use keyword-arg default, mark complete immediately
- Commit after each checkpoint to preserve rollback points
