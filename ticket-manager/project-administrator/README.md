# Project Administrator Metrics Tool

## Purpose

Record per-task activity for every agent and generate a human-facing HTML report.

## Files

- `agent_metrics.py` — SQLite CLI tool.
- `agent_metrics.sqlite3` — local database created on demand.
- `report.html` — generated human report.

## Commands

```zsh
python project-administrator/agent_metrics.py init
python project-administrator/agent_metrics.py record --agent-name backend --feature-name ticket-management --task-description "Implemented validation" --time-spent-minutes 18 --tokens-spent 1420 --model-used claude-3.7-sonnet
python project-administrator/agent_metrics.py summary
python project-administrator/agent_metrics.py gaps
python project-administrator/agent_metrics.py report-html
```

## Preferred agent command

Agents should normally record from their role directories with the wrapper below, because their current working directory is not the repository root:

```zsh
../scripts/report-task-metrics.sh \
  --feature-name 003-agent-api-sdlc \
  --task-id T015 \
  --task-description "Add Platform Authentication section to agents/backend-developer-python.md" \
  --time-spent-seconds 120 \
  --tokens-spent 4800 \
  --model-used claude-sonnet-4-6
```

If exact token counts are unavailable, pass an estimate and mark it explicitly:

```zsh
../scripts/report-task-metrics.sh \
  --feature-name 003-agent-api-sdlc \
  --task-id T015 \
  --task-description "Add Platform Authentication section to agents/backend-developer-python.md" \
  --time-spent-seconds 120 \
  --tokens-spent 4800 \
  --token-source estimated \
  --model-used claude-sonnet-4-6 \
  --notes "Estimated from session usage panel"
```

## Reporting rules

- Every agent records each completed task immediately after finishing it.
- A task is not complete until the agent both writes the SQLite record and sends a brainstorm `task-metrics` message to `project-administrator`.
- Required fields: timestamp, agent name, feature name, short task description, time spent, tokens spent, and model used.
- Prefer exact token counts; otherwise provide a conservative estimate and mark `token_source=estimated`. Use `unknown` only when estimation is impossible and explain why.
- Project Administrator checks for missing or inconsistent entries with `python project-administrator/agent_metrics.py gaps` and asks the relevant agent to correct them.
- The final HTML report groups totals by agent, feature, and model.
- The HTML report now includes dedicated reporting-gap sections so missing tokens, zero-time rows, and reconstructed entries are obvious.
