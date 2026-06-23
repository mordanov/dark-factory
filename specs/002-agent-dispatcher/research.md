# Research: Agent Dispatcher Service

**Feature**: `002-agent-dispatcher`
**Date**: 2026-06-22

## R-001 — Async subprocess runner

**Decision**: `asyncio.create_subprocess_exec` + `asyncio.wait_for(proc.communicate(), timeout)`

**Rationale**: Correct non-blocking pattern. Avoids thread-pool blocking and shell injection.
Drain both stdout/stderr via `communicate()` to prevent pipe deadlock.

**Alternatives considered**:
- `create_subprocess_shell` — rejected (shell injection risk, no benefit)
- `subprocess.run` in executor — rejected (thread-pool exhaustion under concurrent runs)

## R-002 — Service-to-service JWT

**Decision**: `python-jose` HS256 JWT with shared `JWT_SECRET_KEY`.
Fields: `sub=service:agent-dispatcher`, `exp=now+SERVICE_JWT_EXPIRE_HOURS`.
Matches the pattern in `services/orchestrator/src/core/security.py`.

**Rationale**: Zero new infrastructure. All existing services accept this token format.

**Alternatives considered**:
- Static API key — rejected (inconsistent with monorepo auth pattern)
- OAuth2 client credentials — rejected (Keycloak not yet active in this phase)

## R-003 — LLM API runner

**Decision**: `openai.AsyncOpenAI` with messages array `[system, user]`.
Model from `OPENAI_MODEL` env var (default `gpt-4o`).

**Rationale**: Matches `services/orchestrator/` and `services/context-distiller/` pattern.
`OPENAI_API_KEY` is already the configured credential.

**Alternatives considered**:
- Anthropic SDK — valid but OpenAI is the configured provider in the monorepo

## R-004 — Context token truncation

**Decision**: Word-count approximation `len(text.split()) * 1.3` as token estimate.
Truncate `project_memory` at last sentence boundary before limit. Log warning.

**Rationale**: Avoids tiktoken dependency. Sufficient for safety truncation.

**Alternatives considered**:
- tiktoken — accurate but adds startup cost and a new dependency
- Hard character limit — simpler but produces mid-word truncation

## R-005 — Brainstorm mode differences

**Decision**:
- `claude_code` mode: agents use brainstorm-mcp natively (already in MCP config).
  Dispatcher only tracks session/round state in DB.
- `api` mode: Dispatcher prepends previous agents' `tm_comment` values to each subsequent
  agent's context as "Previous agent responses:" block.

**Rationale**: Keeps `claude_code` maximally autonomous; makes `api` mode work without MCP.

## R-006 — Task metrics reporting contract

**Decision**: Every agent context document assembled by `context_builder.py` MUST include
a "## Completion and Metrics Reporting" section that instructs the agent to:

1. Run `bash development/scripts/report-task-metrics.sh` with:
   - `--feature-name` (from ticket's `project_id` or feature branch name)
   - `--task-id` (from ticket ID)
   - `--task-description` (short summary from `[RESULT].summary`)
   - `--time-spent-seconds` (agent's estimate)
   - `--tokens-spent` (agent's estimate; use `--token-source estimated` if unsure)
   - `--model-used` (the model the agent is running on)

2. Send a brainstorm message to `project-administrator` with:
   ```json
   {
     "type": "task-metrics",
     "feature_name": "...",
     "task_id": "...",
     "task_description": "...",
     "time_spent_seconds": 0,
     "tokens_spent": 0,
     "model_used": "...",
     "token_source": "estimated"
   }
   ```

3. Then include the `[RESULT]` block and exit.

This contract mirrors the STEP 5 handshake encoded by `development/run-agents.sh` so that
Dispatcher-launched agents are metrically consistent with agents launched manually.

The `project-administrator` agent (run via `run-agents.sh`) reconciles DB records against
brainstorm messages and produces an HTML report via `agent_metrics.py report-html`.

**Rationale**: Consistency between `run-agents.sh` launches and Dispatcher launches.
Without this, the PA agent's gap-detection will flag all Dispatcher-originated tasks as
unreported, producing noise in the metrics dashboard.
