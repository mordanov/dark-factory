# UX Guidance: Operator-Facing Messages — Capability Registry

**Feature**: 006-capability-registry  
**Author**: designer  
**Date**: 2026-06-26  
**Scope**: Log lines, error messages, and startup output visible to operators (not end-users).

This is a backend infrastructure feature with no user-facing UI. Design scope is limited to operator-observable surfaces: startup logs, error messages, fallback notices, and any text embedded in the code that a human will read when diagnosing a problem.

---

## Guiding Principles

1. **Every error names the file or entity that caused it.** An operator cannot act on "registry invalid" — they can act on `development/agents/registry.yaml: missing required field 'role_id' on agent at index 2`.
2. **Error messages identify what to fix, not just what went wrong.** Include the remediation hint inline where it is short enough (e.g., "Restart the service after editing the file").
3. **Fallback events are logged at WARN, not ERROR.** A fallback is the designed safe path, not a failure. Logging it at ERROR would create alert fatigue.
4. **Startup success is visible and unambiguous.** Operators need to confirm the registry loaded correctly, especially after edits.
5. **No technical stack traces or internal Python tracebacks should reach the operator without a human-readable prefix.** Wrap exceptions with context before propagating.

---

## Surface 1: Registry Load at Startup (FR-014, FR-015)

### Success path

```
INFO  [capability-registry] Loaded 10 agents from development/agents/registry.yaml
```

**Why this wording**: Confirms the file path (so operators know which file was read), the count (so they can immediately spot a truncated or filtered load), and the action (so startup logs are scannable).

### File not found

```
CRITICAL  [capability-registry] Registry file not found: development/agents/registry.yaml
           Service cannot start without a registry. Create the file and restart.
```

**Notes**:
- Use `CRITICAL` (not `ERROR`) because the service will not start — this is a hard failure.
- Include the full path as it was resolved, not just the filename.
- Two-line format: first line states the fact, second line states the action. Do not combine them — operators scan log lines, and the action on its own line is easier to locate.

### File found but unparseable YAML

```
CRITICAL  [capability-registry] Failed to parse development/agents/registry.yaml: {yaml_parse_error}
           Fix the YAML syntax and restart the service.
```

**Notes**:
- Include the raw parser error on the same line (after the colon) so the operator does not need to search for a secondary log entry.
- `{yaml_parse_error}` should be the `str(exception)` from PyYAML — it already includes line/column information.

### File parsed but fails validation

```
CRITICAL  [capability-registry] Invalid registry at development/agents/registry.yaml: {validation_details}
           Service cannot start with an invalid registry. Fix the error and restart.
```

Specific validation messages to implement:

| Condition | Message detail |
|-----------|---------------|
| Duplicate `role_id` | `duplicate role_id 'backend' at agent index 3` |
| Unknown `brainstorm_role` value | `agent 'backend': brainstorm_role must be 'coordinator' or 'contributor', got 'owner'` |
| `fsm_ownership` contains empty string | `agent 'frontend': fsm_ownership contains empty string at index 1` |
| `brainstorm_project_template` missing `{ticket_id}` | `brainstorm_project_template must contain '{ticket_id}', got 'df-session'` |
| Wrong `version` value | `unsupported schema version '2.0' (expected '1.0')` |

---

## Surface 2: Agent Selection (FR-007, FR-008, FR-009)

### Normal selection — single candidate (fast path, no LLM)

No log required. Single-candidate selection is the expected common case; logging it would flood the log.

### Normal selection — multi-candidate with successful LLM response

```
INFO  [agent-selector] ticket={ticket_id} state={fsm_state} candidates=[backend, frontend] → selected=frontend
```

**Notes**:
- Structured one-liner. Include ticket_id so log entries are correlatable.
- Arrow (`→`) visually separates the input context from the decision.

### LLM returned role not in candidates (fallback triggered)

```
WARN  [agent-selector] ticket={ticket_id} state={fsm_state} LLM returned unknown role '{returned_role}' (not in candidates {candidates}); falling back to '{fallback_role}'
```

**Notes**:
- WARN because this indicates an unexpected LLM output — worth investigating if it recurs.
- Include both the invalid value and the candidate list so the operator can tell if the LLM hallucinated a non-existent role or chose a valid-but-wrong one.

### LLM timeout (fallback triggered)

```
WARN  [agent-selector] ticket={ticket_id} state={fsm_state} selection timed out after 10s; falling back to '{fallback_role}'
```

### LLM API error (fallback triggered)

```
WARN  [agent-selector] ticket={ticket_id} state={fsm_state} selection error: {error_summary}; falling back to '{fallback_role}'
```

**Notes for `{error_summary}`**: Use a short human-readable summary, not the full exception class. Examples:
- `connection refused` (not `requests.exceptions.ConnectionError`)
- `rate limited (429)` (not `openai.RateLimitError`)

### Empty candidates list (system-wide fallback)

```
WARN  [agent-selector] ticket={ticket_id} state={fsm_state} no candidates defined for state; defaulting to 'product-manager'
```

**Notes**: This indicates a registry gap (state exists in FSM but no agent owns it). Worth investigating. The product-manager default is the defined safe behavior per spec.

---

## Surface 3: Orchestrator Role Validation (FR-011)

### LLM assigned a role not in the registry

```
WARN  [orchestrator] ticket={ticket_id} LLM assigned unknown role '{assigned_role}'; invoking selector fallback with candidates {candidates}
```

**Notes**:
- This is logged in the orchestrator service, not agent-selector.
- The candidates here are whatever `registry.get_candidates_for_state(to_state)` returns.
- If the candidates list is empty at this point, the agent-selector logs its own empty-candidates WARN.

---

## Surface 4: Brainstorm Participant Discovery (FR-005)

### Participants resolved for architecture review

```
INFO  [brainstorm] ticket={ticket_id} state={fsm_state} participants=[software-architect, security-architect]
```

**Notes**: This confirms that the security-architect is included. Operators debugging missed security reviews can check this log line.

---

## Surface 5: Credentials File (FR-012, FR-013)

### Success

No log required. Credentials writing is an internal implementation detail; a success line would add noise to every spawn.

### Write failure

```
ERROR  [dispatcher] Failed to write credentials for role '{role_id}' to development/{role_id}/credentials.json: {error}
       Agent spawn aborted. Check filesystem permissions on the development/ directory.
```

**Notes**:
- ERROR (not CRITICAL) — the service can continue running for other tickets.
- Two-line format: fact, then remediation.
- Include the full target path so the operator knows exactly where to look.

---

## Surface 6: Registry Injection into Orchestrator Prompt (FR-010)

### Registry section is absent from job payload (degraded mode)

```
WARN  [orchestrator-llm] job_id={job_id} registry_yaml not present in job payload; LLM prompt will not include [AGENT REGISTRY] section
```

**Notes**: This is a backward-compatibility path for jobs triggered outside the dispatcher. Not an error, but operators should know the LLM is operating without registry context.

---

## Accessibility and Observability Requirements

- All log lines must include a component prefix in square brackets (`[capability-registry]`, `[agent-selector]`, `[orchestrator]`, `[brainstorm]`, `[dispatcher]`) to enable log filtering by component.
- All log lines related to a specific ticket must include `ticket={ticket_id}` so operators can trace the full history of one ticket.
- Do not log the `registry_yaml` string content at INFO or DEBUG by default — it is ~3–5 KB and would make logs unreadable. Log it only if a separate `DEBUG_REGISTRY_PAYLOAD` env variable is set.
- Startup CRITICAL messages must terminate the process with a non-zero exit code to prevent silent broken-state deployment.

---

## UX Acceptance Criteria for Backend Agent

These are testable design requirements derived from the guidance above:

| ID | Criterion |
|----|-----------|
| UX-01 | Startup log with 10 successfully loaded agents includes the file path and agent count in a single INFO line. |
| UX-02 | Missing registry file produces a CRITICAL log that includes the resolved file path. |
| UX-03 | Unparseable registry YAML produces a CRITICAL log that includes the YAML parser's line/column error detail. |
| UX-04 | Selection fallback (any cause) produces a WARN log that includes: ticket_id, state, reason, and the chosen fallback role. |
| UX-05 | Selection fallback does NOT produce an ERROR or CRITICAL log. |
| UX-06 | Credentials write failure produces an ERROR log that includes: role_id, full target path, and remediation hint. |
| UX-07 | All logs relating to a specific ticket include `ticket={ticket_id}`. |
| UX-08 | The raw `registry_yaml` string is not present in INFO or WARN log output under normal operation. |
| UX-09 | Startup failure (CRITICAL) exits the process with a non-zero exit code. |
| UX-10 | Brainstorm participant log line for `architecture_review` state includes both `software-architect` and `security-architect`. |
