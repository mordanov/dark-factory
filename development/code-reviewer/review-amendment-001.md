# Review Amendment 001: Path Traversal Blocker

**Date**: 2026-06-23  
**Amends**: review-phase1-3  
**Finding escalated**: Missed Blocker — `agent_id` path traversal (security-architect raised, confirmed by PM)

---

## Blocker: `agent_id` from ticket used directly in path construction — path traversal vulnerability

**Location**: `src/services/dispatcher_service.py:45` and `src/services/brainstorm_coordinator.py:41`  
**Issue**: `prompt_path = Path(settings.agent_prompts_dir) / f"{agent_id}.md"` where `agent_id` comes directly from `ticket.assigned_agent` — untrusted external data from the Orchestrator API response. No whitelist or path-traversal guard exists. An attacker who can write to a ticket's `assigned_agent` field (or compromise the Orchestrator) can pass values like `../../../etc/passwd` or `../../secrets/.env` to read arbitrary files from the container filesystem, returned as the "system prompt" to a real agent.

**Impact**: Arbitrary file read from the container. With `ClaudeCodeRunner` the file contents are passed as `--system-prompt` to a Claude Code subprocess, which would execute under that attacker-controlled "system prompt". This is a security vulnerability that enables both information disclosure and prompt injection.

**Required action** (both sites — `dispatcher_service.py` and `brainstorm_coordinator.py`):

1. **Whitelist validation**: Derive valid agent IDs from the prompts directory at startup:
   ```python
   VALID_AGENT_IDS = {p.stem for p in Path(settings.agent_prompts_dir).glob("*.md")}
   if agent_id not in VALID_AGENT_IDS:
       # mark failed, call reporter, return
   ```
2. **Path containment check** (defence in depth, even after whitelist):
   ```python
   prompts_dir = Path(settings.agent_prompts_dir).resolve()
   prompt_path = (prompts_dir / f"{agent_id}.md").resolve()
   if not str(prompt_path).startswith(str(prompts_dir)):
       # reject
   ```

**Evidence**: `agent_id = ticket.assigned_agent` at `dispatcher_service.py:25`; no sanitisation before `Path(...) / f"{agent_id}.md"` at line 45. Same pattern in `brainstorm_coordinator.py:41`.

**Why missed in initial review**: I verified that `prompt_path.exists()` was checked before use (preventing crashes) but did not verify that the path was constrained to the prompts directory. The check only guards against missing files, not adversarial path construction.

---

## Revised Decision

**CHANGES REQUESTED** (previously: APPROVED WITH COMMENTS)

This Blocker must be fixed before Phase 3 implementation proceeds. The fix is localised to two files and straightforward to implement.

### Updated Required Actions (supersedes review-phase1-3 for Phase 3 gate)

| Priority | Item | Owner |
|----------|------|-------|
| **Blocker — fix immediately** | `agent_id` whitelist + path containment check in `dispatcher_service.py` and `brainstorm_coordinator.py` | backend |
| Must fix before Phase 6 | COUNT(*) in `list_all` | backend |
| Must fix before Phase 6 | PostgreSQL test DB for integration tests | backend + autotester |
| Must fix before Phase 3 sign-off | Orphan sweep passes real `project_id` | backend |
| Must fix before Phase 3 sign-off | Wire `OPENAI_BASE_URL` through config and api_runner | backend |

All other findings from review-phase1-3 stand unchanged.
