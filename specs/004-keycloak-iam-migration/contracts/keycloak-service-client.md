# Contract: KeycloakServiceClient (keycloak_client.py)

**Applies to**: orchestrator, context-distiller, agent-dispatcher, agent-tools,
  user-input-manager (for TM calls), ticket-manager (for any outbound service calls)
**Date**: 2026-06-24

---

## Interface

```python
# src/core/keycloak_client.py (each service — identical pattern)

class KeycloakServiceClient:
    def __init__(
        self,
        keycloak_base_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
    ) -> None: ...

    async def get_token(self) -> str:
        """Return a valid Bearer token for outbound service calls.

        Token is fetched via Client Credentials grant and cached until 30s before expiry.
        Uses asyncio.Lock to prevent thundering-herd on concurrent cache misses.

        Raises:
            UpstreamError — if Keycloak returns non-200 on token endpoint
        """

    async def async_auth_headers(self) -> dict[str, str]:
        """Return {"Authorization": "Bearer <token>"} for use in httpx calls."""
```

### Module-level singleton pattern (all services)

```python
# src/core/keycloak_client.py
_kc_client: KeycloakServiceClient | None = None

def get_kc_client() -> KeycloakServiceClient:
    global _kc_client
    if _kc_client is None:
        settings = get_settings()
        _kc_client = KeycloakServiceClient(
            keycloak_base_url=settings.keycloak_base_url,
            realm=settings.keycloak_realm,
            client_id=settings.keycloak_client_id,
            client_secret=settings.keycloak_client_secret,
        )
    return _kc_client
```

---

## Behaviour Contracts

### C-KC-01: Token is cached until 30s before expiry
- First call: fetches from `{base_url}/realms/{realm}/protocol/openid-connect/token`
- Subsequent calls where `now < expires_at - 30s`: return cached token, no HTTP call
- At `expires_at - 30s`: refresh triggered on next call

### C-KC-02: asyncio.Lock prevents concurrent fetches
- Two simultaneous coroutines calling `get_token()` when cache is stale:
  - First acquires lock → fetches → updates cache → releases lock
  - Second acquires lock after first → sees fresh cache → returns immediately

### C-KC-03: Keycloak error raises UpstreamError
- If Keycloak token endpoint returns non-200: raise `UpstreamError`
- If network timeout: raise `UpstreamError`
- Caller is responsible for propagating error (service startup or request handler)

### C-KC-04: Client secret never appears in logs or exceptions
- `UpstreamError` message MUST NOT include the client secret
- structlog binds client_id but never client_secret

---

## Service-Specific Keycloak Client IDs

| Service | `keycloak_client_id` | Purpose |
|---------|---------------------|---------|
| orchestrator | `orchestrator` | TM API calls |
| context-distiller | `context-distiller` | inbound validation only |
| agent-dispatcher | `agent-dispatcher` | TM + Orchestrator calls + agent token injection |
| agent-tools | `agent-tools` | inbound validation only |
| user-input-manager | `user-input-manager` | TM + Orchestrator + ContextDistiller calls |
| ticket-manager | `ticket-manager` | inbound validation only |

---

## Replacement in Existing Callers

### orchestrator: tm_client/client.py

```python
# BEFORE
async def _login(self) -> None:
    resp = await c.post(f"{self._base}/api/auth/login", json={...})
    self._token = resp.json()["access_token"]

async def _headers(self) -> dict:
    if not self._token:
        await self._login()
    return {"Authorization": f"Bearer {self._token}"}

# AFTER
from src.core.keycloak_client import get_kc_client

async def _headers(self) -> dict:
    return await get_kc_client().async_auth_headers()
```

### agent-dispatcher: reporter.py

```python
# BEFORE
from src.core.security import create_service_token
token = create_service_token()
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# AFTER
from src.core.keycloak_client import get_kc_client
headers = {**await get_kc_client().async_auth_headers(), "Content-Type": "application/json"}
```

### agent-dispatcher: context_builder.py (token injection for agents)

```python
# NEW: inject fresh token into agent context
kc_client = get_kc_client()
service_token = await kc_client.get_token()
context_parts.append(f"""
## Service Token
Use this Bearer token for ALL API calls to Dark Factory services.
Token is valid for 1 hour from agent spawn time.

Authorization: Bearer {service_token}

TM API base: {settings.ticket_manager_base_url}
""")
```

---

## Test Contract: unit/test_keycloak_client.py (per service)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_get_token_calls_keycloak_token_endpoint` | Cold cache | httpx.post to correct URL; returns token string |
| `test_token_cached_until_expiry` | Two calls, token fresh | httpx.post called exactly once |
| `test_token_refreshed_30s_before_expiry` | expires_at - now < 30s | httpx.post called on second call |
| `test_concurrent_calls_use_single_request` | Two async tasks simultaneously on cold cache | httpx.post called exactly once (Lock works) |
| `test_keycloak_error_raises_upstream_error` | Keycloak returns 500 | UpstreamError raised |
