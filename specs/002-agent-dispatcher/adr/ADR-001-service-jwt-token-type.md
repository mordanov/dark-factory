# ADR 001: Service JWT Token Type for Agent Dispatcher Outbound Calls

## Status
Accepted

## Context
The Agent Dispatcher calls other Dark Factory services (Orchestrator, Ticket Manager,
Context Distiller) using short-lived JWTs it mints itself with `create_service_token()`.

The Orchestrator's `verify_access_token()` (and all other services that share the same
`JWT_SECRET_KEY`) reject tokens whose payload does not contain `"type": "access"`:

```python
if payload.get("type") != "access":
    raise JWTError("Not an access token")
```

The initial Dispatcher implementation emitted `"type": "service"`, causing every
outbound call to return HTTP 401.

## Decision Drivers
- All services in the monorepo share a single `JWT_SECRET_KEY` and the same token
  format enforced by their `verify_access_token` implementations.
- No new auth infrastructure is planned for this phase (Keycloak deferred).
- Service-to-service calls must pass existing token validation without modifying
  receiving services.

## Options Considered

### Option A — Use `"type": "access"` with a service `sub`
- Pros: Accepted by all existing `verify_access_token` implementations without change.
  `sub = "service:agent-dispatcher"` is still distinguishable from user tokens.
- Cons: Token type semantics are stretched; a service token and a human access token
  share the same `type` value.
- Risks: If a future audit policy distinguishes service from human tokens by `type`,
  these tokens will need migration.

### Option B — Use `"type": "service"` and update all `verify_access_token` receivers
- Pros: Cleaner semantic separation.
- Cons: Requires coordinated changes across five services. Constitution change needed.
  Blocked until all services are updated atomically.
- Risks: High coordination cost; breaks if one service is not updated.

### Option C — Use a static API key header (`X-Service-Key`)
- Pros: No JWT library needed for service auth.
- Cons: Inconsistent with monorepo auth pattern. Requires new header handling in every
  receiving service.

## Decision
Use **Option A**: emit `"type": "access"` with `sub = "service:agent-dispatcher"`.

This is the only option that works without modifying receiving services. The service
`sub` prefix remains distinguishable for audit and future policy enforcement.

## Consequences

**Positive**
- All outbound service calls from the Dispatcher are accepted by existing services
  immediately — no receiver changes needed.
- Consistent with how the Orchestrator generates its own service tokens.

**Negative**
- Human access tokens and service tokens share `type = "access"`. Future
  differentiation requires a constitution amendment and coordinated migration.

**Operational/Security Impact**
- Service tokens are short-lived (`SERVICE_JWT_EXPIRE_HOURS`, default 1 hour).
- Tokens are logged at WARNING level if they appear in raw_output (stripped by
  `_strip_service_jwt()` before DB storage).
- If `JWT_SECRET_KEY` is rotated, all active service tokens are invalidated
  immediately — the Dispatcher generates a fresh token per call so recovery is
  automatic on the next invocation.

## Validation and Fitness Functions
- Integration test: `Reporter._trigger_orchestrator()` returns 201, not 401, when
  called with a token produced by `create_service_token()`.
- Security test: Assert that `raw_output` stored in `agent_runs` does not contain
  the JWT value used during that run (verify `_strip_service_jwt` applied).

## Reversal or Migration Strategy
To introduce a distinct `"type": "service"` token:
1. Add `"service"` to the accepted types whitelist in all five receiving services
   in a single coordinated PR.
2. Update `create_service_token()` to emit `"type": "service"`.
3. Deprecate and remove the whitelist entry for `"service"` in human-auth paths.
