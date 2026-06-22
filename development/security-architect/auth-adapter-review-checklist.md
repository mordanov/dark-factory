# Security Review Checklist: Auth Adapters (T032–T041)

**Feature**: 001-monorepo-unification  
**Date**: 2026-06-22  
**Reviewer**: security-architect agent  
**Applies to**: backend agent implementing T032–T041  
**Reference**: contracts/auth-adapter-interface.md, threat-model.md

---

## Per-File Checklist

For each `auth_adapter.py` (T032–T036) and each `dependencies.py` update (T037–T041):

### AUTH_MODE Handling (Blocker-level)

- [ ] **A1** — `AUTH_MODE=local`: `verify()` delegates to the existing, unchanged `security.verify_access_token()` call. No new token parsing, no new claims extraction, no new secret loading.
- [ ] **A2** — `AUTH_MODE=keycloak`: `verify()` raises `NotImplementedError` immediately. No token is inspected, no claims returned, no partial validation attempted.
- [ ] **A3** — `AUTH_MODE=<anything else>`: `verify()` (or `__init__` / module load) raises `ValueError` with a clear message. The service MUST NOT start or process requests with an unrecognised mode.
- [ ] **A4** — `AUTH_MODE` is read from `settings` (injected) — not from `os.environ` directly inside `verify()`. Value is resolved once and validated at construction time or module load.
- [ ] **A5** — No default value silently applied to `AUTH_MODE`. If the env var is missing entirely, the service fails with a configuration error.

### Isolation (Blocker-level)

- [ ] **A6** — This `auth_adapter.py` imports ONLY from within its own service's source tree. No cross-service imports.
- [ ] **A7** — No shared adapter base class imported from a shared library package outside this service directory.

### Token Handling (High)

- [ ] **A8** — Token string is passed through to `security.verify_access_token()` without modification (no trimming, no base64 re-encoding, no claims pre-extraction).
- [ ] **A9** — `JWTError` and any `UnauthorizedError` from the local validation layer propagate unchanged to the FastAPI dependency. No swallowing of auth errors.
- [ ] **A10** — `verify()` is `async`; existing sync `verify_access_token()` calls are wrapped with `asyncio.run_in_executor` or are already async — verify no blocking call on async event loop.

### FastAPI Dependency (High)

- [ ] **A11** — `NotImplementedError` from `verify()` is caught in `dependencies.py` and returns HTTP 501. It MUST NOT propagate as HTTP 500.
- [ ] **A12** — `JWTError`/`UnauthorizedError` from `verify()` is caught and returns HTTP 401. It MUST NOT propagate as HTTP 500.
- [ ] **A13** — No token value is logged in the dependency or adapter. The `claims` dict is also not logged in full (may contain PII).
- [ ] **A14** — The `ValueError` (unrecognised `AUTH_MODE`) raised at startup/construction is NOT caught silently in the dependency — it should prevent service startup, not be swallowed per-request.

### Ticket-Manager Python 3.12 Upgrade (T042 — Medium)

- [ ] **A15** — Dockerfile base image changed from `python:3.11-slim` to `python:3.12-slim`. No other base image used.
- [ ] **A16** — `pyproject.toml` `requires-python = ">=3.12"`.
- [ ] **A17** — `python-jose==3.3.0` (canonical) used — confirm it is not downgraded below canonical version.
- [ ] **A18** — `pytest-asyncio==0.24.0` (canonical) replaces any `1.3.0` reference — no deprecated fixture patterns introduced.

---

## Security Test Cases to Verify (per service)

Code Reviewer and Autotester should confirm these pass for each service:

| ST | Service | Test |
|---|---|---|
| ST-01 | all 5 | `AUTH_MODE=local` + valid token → HTTP 200 |
| ST-02 | all 5 | `AUTH_MODE=local` + expired token → HTTP 401 |
| ST-03 | all 5 | `AUTH_MODE=local` + tampered token → HTTP 401 |
| ST-04 | all 5 | `AUTH_MODE=keycloak` + any token → HTTP 501 |
| ST-05 | all 5 | `AUTH_MODE=ldap` (unrecognised) → service startup fails, process exits non-zero |

---

## Review Result Template

After implementing T032–T041, backend agent should request security review. Security architect will issue:

```
## Security Review Result: Auth Adapters

### Decision
APPROVED | APPROVED WITH RISKS | CHANGES REQUIRED

### Blockers (A1–A7 failures)
### High Findings (A8–A14 failures)
### Medium Findings (A15–A18 failures)
### Security Tests Status (ST-01 through ST-05)
### Residual Risks
```
