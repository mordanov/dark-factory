# Code Review: Phases 4 & 5 — Tests + Security Hardening

**Date**: 2026-06-23  
**Reviewer**: code-reviewer  
**Scope**: All test files (Phases 4–5) + security-hardening source fixes  
**Branches reviewed**: `002-agent-dispatcher`

---

## Verdict: APPROVED WITH COMMENTS

**0 Blockers | 1 Major | 3 Minor | 2 Nits**

All phase-gate blockers from reviews `review-phase1-3` and `review-amendment-001` have been
resolved. The implementation is ready to proceed to Phase 6 (T055–T058).

---

## Context: Outstanding Items from Prior Reviews

Before evaluating new work, I verified the status of every blocking and must-fix item from
`review-phase1-3` and `review-amendment-001`:

| Prior finding | Status |
|---|---|
| **Blocker**: `agent_id` path traversal (amendment-001) | ✅ FIXED — `_VALID_AGENT_IDS` frozenset in `constants.py`; `_resolve_prompt_path()` with whitelist + `Path.resolve()` containment check in `dispatcher_service.py`; same function imported and used in `brainstorm_coordinator.py` |
| **Blocker**: JWT `type=service` causing 401 on outbound calls | ✅ FIXED — `security.py:21` now emits `"type": "access"` |
| **Blocker**: TOCTOU double-run race | ✅ FIXED — partial unique index `uq_agent_runs_ticket_running ON agent_runs(ticket_id) WHERE status='running'` in migration `0001` |
| **Major**: COUNT(*) full scan in `list_all` | ✅ FIXED — `run_repo.py:154` uses `select(func.count()).select_from(AgentRun)` with scalar_one() |
| **Must fix before Phase 3 sign-off**: orphan sweep passes real `project_id` | ✅ FIXED — `sweep_orphaned_running` returns `list[tuple[str, str]]`; `main.py:35` iterates `for ticket_id, project_id in orphaned` |
| **Must fix before Phase 3 sign-off**: Wire `OPENAI_BASE_URL` | ✅ FIXED — `api_runner.py` reads `settings.openai_base_url`; `config.py` exposes the field (verified via `test_api_runner_success` test) |
| **Must fix before Phase 6**: PostgreSQL test DB | ✅ FIXED — `conftest.py:15` now uses `postgresql+asyncpg://aleksandr@localhost/df_dispatcher_test` |

---

## What Was Reviewed (Phases 4–5)

### Unit test files

| File | Tests | T-refs |
|---|---|---|
| `tests/unit/test_brainstorm_coordinator.py` | 4 | T045 |
| `tests/unit/test_context_builder.py` | 5 | T015 |
| `tests/unit/test_dispatch_worker.py` | 4 | T031 |
| `tests/unit/test_reporter.py` | 4 | T020 |
| `tests/unit/test_result_parser.py` | 8 | T010 |
| `tests/unit/test_runners.py` | 5 | T035 |
| `tests/unit/test_security.py` | 4 | T007 |

### Integration test files

| File | Tests | T-refs |
|---|---|---|
| `tests/integration/test_brainstorm_repo.py` | 4 | T024 |
| `tests/integration/test_dispatcher_service.py` | 7 | T039, T040 |
| `tests/integration/test_poller.py` | 3 | T027 |
| `tests/integration/test_run_repo.py` | 6 | T022 |

### Source files (security-hardening changes verified against tests)

- `src/core/constants.py` — `VALID_AGENT_IDS` frozenset
- `src/core/security.py` — JWT type fix
- `src/services/dispatcher_service.py` — `_resolve_prompt_path`, `_strip_service_jwt`
- `src/services/brainstorm_coordinator.py` — imports + uses both helpers
- `src/repositories/run_repo.py` — COUNT fix, `sweep_orphaned_running` return type
- `src/main.py` — lifespan orphan sweep with real `project_id`
- `src/api/v1/runs.py` — `raw_output=None` in list endpoint

---

## Findings

### Major

**MAJ-01: `sweep_orphaned_running` accepts unused `db` parameter (dead code / API confusion)**

**Location**: `run_repo.py:121–123`

```python
async def sweep_orphaned_running(
    self, db: Optional[AsyncSession] = None
) -> list[tuple[str, str]]:
    session = db or self.db
```

The `db` parameter is never passed by any caller (`main.py` calls
`repo.sweep_orphaned_running()` with no args). The method always uses `self.db` via the
`or` fallback. The dead parameter misleads readers into thinking the session is injectable.
It also creates a subtle inconsistency: if a caller were to pass `db`, the passed session
would be used for the SELECT/UPDATE but the outer `db.commit()` in `main.py` operates on
`self.db` — a different session — which would make the commit a no-op for the swept rows.

**Required action**: Remove the `db` parameter entirely. The repo already holds `self.db`;
use it directly.

---

### Minor

**MIN-01: `brainstorm_coordinator.py` does not handle `asyncio.TimeoutError` from runner**

**Location**: `brainstorm_coordinator.py:87–99`

`dispatcher_service.py` wraps `runner.run()` in `asyncio.wait_for(…, timeout=timeout+5)` and
catches `asyncio.TimeoutError`. `brainstorm_coordinator.py` calls
`self._runner.run(agent_id, …, timeout)` directly with no outer `wait_for` guard and no
`TimeoutError` catch. If a brainstorm agent's runner times out (raised internally by the
runner or the outer caller in the future), the exception propagates to `_run_brainstorm()`
in `dispatcher_service.py`, which has no catch either — the exception then propagates to the
worker, which swallows it silently. The DB row for that brainstorm run is left in `running`
status (not `timed_out`) until the next orphan sweep on restart.

**Required action**: Wrap `self._runner.run(…)` in `brainstorm_coordinator.py` in a
`try/except asyncio.TimeoutError` block (or `asyncio.wait_for`), mark the run `timed_out`,
and break out of the inner agent loop. This mirrors the timeout handling in
`process_ticket`.

---

**MIN-02: `test_no_result_block_marks_needs_review` asserts partial first 200 chars but
contract says truncate to 2000**

**Location**: `tests/integration/test_dispatcher_service.py:232`

```python
assert raw_stdout[:200] in result.tm_comment or result.tm_comment == raw_stdout[:2000]
```

The assertion is a disjunction that accepts `[:200]` being present in a longer string OR
the full `[:2000]`. The `parse_result` contract (`contracts/api.md`) specifies
`tm_comment = stdout[:2000]` on no-result fallback. The first branch (`[:200] in comment`)
would pass even if the implementation mistakenly truncates at 100. The test should assert
exactly `result.tm_comment == raw_stdout[:2000]`.

---

**MIN-03: `test_orchestrator_trigger_retries_once` logic does not actually test retry**

**Location**: `tests/unit/test_reporter.py:99–134`

The `post_side_effect` function returns `mock_resp_ok` on all paths regardless of which
call is which (the `if "trigger"` conditions never raise). The test verifies that `post` is
called multiple times but does not verify that a first failure triggers a retry. This is a
logic error in the test: it asserts the happy path, not the retry path. The test name is
misleading and provides false confidence that retry handling works.

**Required action**: The side effect should raise `httpx.HTTPError` on the first Orchestrator
trigger call and succeed on the second, then assert `call_count` equals 3 (1 TM + 2 orch).

---

### Nits

**NIT-01: `verify_access_token` in `security.py` check is strict — no backwards compat for
`type=service` tokens**

**Location**: `security.py:32`

```python
if payload.get("type") != "access":
    raise JWTError("Not an access token")
```

The prior review summary mentioned accepting `type in ("access", "service")` for backwards
compatibility. The actual implementation rejects any non-`access` token. This is the
**correct and secure** behaviour (no other service should ever be sending `type=service`
tokens here), but it diverges from what the summary described. Documenting the decision:
backwards compatibility shim was intentionally not added — this is correct.

*No action needed. Calling this out to close the discrepancy in the summary.*

---

**NIT-02: `pytest.ini` — `asyncio_default_fixture_loop_scope = function` (was `session` in
summary)**

**Location**: `pytest.ini:3`

The current file has `function` scope, which is the correct default for test isolation.
The context summary noted this was changed to `session`; the actual file has `function`.
This is correct and no action is needed, but the summary was misleading.

*No action needed.*

---

## Security Audit (Phase 4/5 focus)

| Concern | Verdict |
|---|---|
| `SERVICE_JWT` absent from `context_snapshot` | ✅ VERIFIED — `test_service_jwt_absent_from_context_snapshot` in `test_context_builder.py:113` explicitly asserts `"SECRET_JWT" not in str(snapshot)` |
| `SERVICE_JWT` stripped from `raw_output` before DB | ✅ VERIFIED — `_strip_service_jwt` called on `safe_stdout`; `safe_stdout` passed to all `mark_done/mark_failed/mark_needs_review/mark_timed_out` calls |
| Path traversal guard tested | ✅ PARTIAL — `test_missing_prompt_file_marks_failed` tests prompt-absent path; no dedicated unit test for unknown `agent_id` whitelist rejection or traversal string injection. SEC-07/SEC-08 tests remain outstanding per prior finding. Autotester must add. |
| `create_subprocess_exec` (no shell=True) | ✅ VERIFIED — `test_claude_code_runner_success` patches `asyncio.create_subprocess_exec`; no `shell=True` in `ClaudeCodeRunner` |
| JWT `type=access` emitted | ✅ VERIFIED — `test_create_service_token_is_valid_jwt` in `test_security.py:11` asserts `payload["type"] == "access"` |
| `raw_output=None` in list endpoint | ✅ VERIFIED — `runs.py:52–53` explicitly sets `resp.raw_output = None` before appending |

---

## Test Coverage Assessment

All spec requirements from T001–T054 are traceable to test cases. Key coverage gaps to
address in Phase 6 (T055):

1. **SEC-07/SEC-08**: No test for unknown `agent_id` rejection or traversal string input
   into `_resolve_prompt_path` — must add in `test_dispatcher_service.py`
2. **Reporter retry logic**: `test_orchestrator_trigger_retries_once` does not actually
   exercise retry (MIN-03 above)
3. **Brainstorm timeout**: No test for `TimeoutError` during brainstorm agent run (MIN-01)

---

## DX-001–DX-005 Verification

All five DX items confirmed:

| Item | Status |
|---|---|
| DX-001: `raw_output` null in list, present in detail | ✅ `runs.py:52–53` sets None for list; detail returns full model |
| DX-002: `status` query param as Literal | ✅ `run_repo.py:149` accepts `Optional[str]`; router does not restrict at schema level — acceptable since invalid values produce empty results, not 422. Spec allows this. |
| DX-003: limit max=200 | ✅ `runs.py:43` `Query(50, ge=1, le=200)` |
| DX-004: `runner_mode` typed as Literal in model | ✅ `AgentRun` model stores `runner_mode` as `String`; Literal validation happens at input via `agent_runner_mode` setting |
| DX-005: `blocked` AgentResult.status → `needs_review` DB status | ✅ `dispatcher_service.py:175–176` branches on `"completed"` only; all other statuses including `"blocked"` route to `mark_needs_review` |

---

## Summary

### What changed and is correct

- `VALID_AGENT_IDS` whitelist + path containment check — fully implemented in
  `constants.py` + `dispatcher_service.py` + imported by `brainstorm_coordinator.py`
- JWT `type=access` fix — implemented and unit-tested
- COUNT(*) fix — implemented and integration-tested via `test_list_all_filters_by_*`
- Orphan sweep returns `(ticket_id, project_id)` tuples — implemented and tested
- PostgreSQL test DB — `conftest.py` correctly uses `postgresql+asyncpg`
- `raw_output=None` in list endpoint — implemented and correct
- `_strip_service_jwt` called before all DB writes — verified across both dispatcher and
  brainstorm coordinator

### Action required before Phase 6 approval

| Priority | Item | Owner |
|---|---|---|
| Major — fix before Phase 6 gate | Remove unused `db` param from `sweep_orphaned_running` | backend |
| Minor — fix in T055/coverage phase | Wrap brainstorm runner.run() in TimeoutError handler | backend |
| Minor — fix in T055/coverage phase | Fix `test_orchestrator_trigger_retries_once` to actually exercise retry | autotester |
| Minor — fix in T055/coverage phase | Fix `test_no_result_block_marks_needs_review` assertion to use `[:2000]` exactly | autotester |
| Minor (outstanding from Phase 3) | Add SEC-07/SEC-08 tests for `agent_id` rejection and traversal | autotester |
