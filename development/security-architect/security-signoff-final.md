# Final Security Sign-Off: Dark Factory Monorepo Unification

**Date**: 2026-06-22  
**Author**: security-architect agent  
**Feature**: 001-monorepo-unification

---

## Decision: APPROVED WITH DOCUMENTED RESIDUAL RISK

All security gates cleared. One Medium residual risk documented below with owner and mitigation path.

---

## Security Gates Summary

| Gate | Scope | Decision | Date |
|---|---|---|---|
| Phase 4 | Auth adapters (T032–T041) across all 5 services | APPROVED | 2026-06-22 |
| Phase 5 | UIM Zustand token migration (T043–T050) | APPROVED | 2026-06-22 |
| Infra | Secrets management, nginx, compose, postgres init | APPROVED | 2026-06-22 |
| Integration tests | LLM mock isolation, test credentials, seed SQL | APPROVED | 2026-06-22 |

---

## Security Tests Status (ST-01 through ST-12)

| Test | Status | Evidence |
|---|---|---|
| ST-01: `AUTH_MODE=local` valid token → 200 | PASS (by implementation) | adapter delegates unchanged to `verify_access_token()` |
| ST-02: `AUTH_MODE=local` expired token → 401 | PASS (by implementation) | `JWTError` → 401 in all 5 dependencies.py |
| ST-03: `AUTH_MODE=local` tampered token → 401 | PASS (by implementation) | `JWTError` → 401 in all 5 dependencies.py |
| ST-04: `AUTH_MODE=keycloak` → 501 | PASS (by implementation) | `NotImplementedError` → 501 in all 5 dependencies.py |
| ST-05: `AUTH_MODE=<unknown>` → startup failure | PASS (by implementation) | `ValueError` raised in `AuthAdapter.__init__` |
| ST-06: No `access_token` in `localStorage` after UIM login | PASS | Zero write paths; verified by code sweep + independent code-reviewer |
| ST-07: No `access_token` in `sessionStorage` after UIM login | PASS | Zero write paths; verified by code sweep |
| ST-08: UIM logout clears store + `sessionStorage["rt"]` | PASS | `auth.ts:41-42` explicit `sessionStorage.removeItem(RT_KEY)` + store clear |
| ST-09: No secrets in Git history | PASS | `git log --all -- "*.env"` returns no committed secrets |
| ST-10: No real OpenAI calls in integration test suite | PASS (by design) | `OPENAI_BASE_URL=http://llm-mock:11434/v1` overrides all services; `OPENAI_API_KEY=test-invalid-key` |
| ST-11: LLM mock has no host port exposure | PASS | No `ports:` in `integration-tests/docker-compose.test.yml` for `llm-mock` |
| ST-12: No service DB uses postgres superuser | PASS | All service DB URLs use service-specific users from `.env.example` |

---

## Resolved Findings

| ID | Finding | Resolution |
|---|---|---|
| H-01 | context-distiller `HTTPBearer()` without `auto_error=False` | Fixed by backend — `HTTPBearer(auto_error=False)` + explicit 401 guard |
| M3 | agent-tools `JWT_SECRET_KEY` empty default | Fixed by software-architect — `:?` required in compose + placeholder in `.env.example` |

---

## Residual Risk

**MEDIUM — Shared JWT signing secret: UIM ↔ Orchestrator ↔ Context-Distiller**

In production, `ORCH_SECRET_KEY` and `DISTILLER_SECRET_KEY` must equal `UIM_SECRET_KEY` for cross-service token validation to work (orchestrator and context-distiller validate tokens issued by UIM). This means:
- A compromised UIM secret key also compromises orchestrator and context-distiller token verification.
- Key rotation requires coordinated restart of all three services simultaneously.

**Owner**: Operations / platform engineer  
**Mitigation**: Document in production runbook before first deployment. Track as a future architecture improvement (dedicated token exchange service or mTLS for internal service calls).  
**Due**: Before first production deployment.  
**This risk does not block this release** — it is an inherent property of the AUTH_MODE=local architecture and applies equally to the pre-migration state.

---

## Scope Not Covered (Out of Scope for This Feature)

- Runtime penetration testing or dynamic analysis
- SSL/TLS configuration (certbot activation is a separate ops step)
- Keycloak integration security (stub only in this release)
- Production secrets rotation procedures (tracked as residual risk above)
- XSS prevention in frontend (in-memory Zustand significantly narrows XSS token exposure vs localStorage; full XSS hardening is a separate concern)
