# Contract: Orchestrator Job Trigger Payload — Brainstorm Transcript Extension

## Overview

The `agent-dispatcher` extends the existing Orchestrator job trigger payload with a `brainstorm_transcript` key when an `architecture_review` brainstorm round has completed. This is an additive extension — the payload remains backward-compatible.

## Endpoint

```
POST /api/v1/jobs/trigger
Host: orchestrator:8000
Content-Type: application/json
```

## Payload Schema

```json
{
  "ticket_id": "<string>",
  "project_id": "<string>",
  "registry_yaml": "<string>",
  "brainstorm_transcript": {
    "project_name": "<string>",
    "round_number": "<integer>",
    "max_rounds": "<integer>",
    "consensus": "agreed | disagreed | inconclusive",
    "messages": [
      {
        "author": "<string>",
        "content": "<string>",
        "timestamp": "<string>"
      }
    ]
  }
}
```

## Field Semantics

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `brainstorm_transcript` | object | No | Present only for `architecture_review` tickets after a round completes |
| `brainstorm_transcript.project_name` | string | Yes (if present) | The brainstorm session project name, e.g., `"df-TKT-001"` |
| `brainstorm_transcript.round_number` | integer | Yes | Which round this transcript was captured after |
| `brainstorm_transcript.max_rounds` | integer | Yes | Maximum configured rounds (context for WAIT decision) |
| `brainstorm_transcript.consensus` | string | Yes | Derived consensus: `"agreed"`, `"disagreed"`, or `"inconclusive"` |
| `brainstorm_transcript.messages` | array | Yes | All messages posted by agents in the session (may be empty `[]`) |
| `messages[].author` | string | Yes | Agent role ID (e.g., `"software-architect"`) |
| `messages[].content` | string | Yes | Message text |
| `messages[].timestamp` | string | Yes | ISO8601 or empty string if not provided by CLI |

## Orchestrator Behaviour

When `brainstorm_transcript` is present:
- The LLM prompt includes a `[BRAINSTORM TRANSCRIPT]` section with all messages and consensus
- The Orchestrator uses this to evaluate the `architecture_consistency` gate

When `brainstorm_transcript` is absent and `fsm_status == "architecture_review"`:
- The LLM prompt includes a `[BRAINSTORM TRANSCRIPT]` section with a WAIT hint
- The Orchestrator should not evaluate the gate until a transcript is available

When `brainstorm_transcript` is absent and `fsm_status != "architecture_review"`:
- No `[BRAINSTORM TRANSCRIPT]` section appears in the LLM prompt

## Example

```json
{
  "ticket_id": "TKT-001",
  "project_id": "proj-alpha",
  "registry_yaml": "version: \"1.0\"\nagents: ...",
  "brainstorm_transcript": {
    "project_name": "df-TKT-001",
    "round_number": 1,
    "max_rounds": 3,
    "consensus": "inconclusive",
    "messages": [
      {
        "author": "software-architect",
        "content": "I recommend event sourcing for the audit log.",
        "timestamp": "2026-06-27T10:00:00Z"
      },
      {
        "author": "security-architect",
        "content": "Agreed, but we must add immutable log storage.",
        "timestamp": "2026-06-27T10:01:00Z"
      }
    ]
  }
}
```
