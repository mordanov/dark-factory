# Test Strategy: Keycloak IAM Migration (004)

**Feature**: 004-keycloak-iam-migration  
**Date**: 2026-06-24  
**Author**: Autotester Agent  
**Spec**: `specs/004-keycloak-iam-migration/spec.md`

---

## Scope

All 4 user stories and their acceptance criteria:

- **US1** — SSO login via keycloak-js (P1)
- **US2** — Admin user management via Keycloak console (P2)
- **US3** — Service-to-service auth via Client Credentials (P3)
- **US4** — Destructive database migrations, data integrity (P4)

Plus all 8 success criteria (SC-001 to SC-008) and 3 security blockers (BLK-01, BLK-02, BLK-03).

---

## Test Levels and Ownership

### Unit Tests (autotester — T070-T078, written)

**`test_auth_adapter.py`** — 11 tests per service × 6 services = 66 tests total

| Test | Requirement |
|------|-------------|
| `test_valid_user_token_returns_claims` | C-AUTH-01 |
| `test_valid_admin_token_has_is_admin_true` | C-AUTH-01 |
| `test_invalid_token_raises_unauthorized` | C-AUTH-02 |
| `test_expired_token_raises_unauthorized` | C-AUTH-02 |
| `test_missing_realm_access_returns_empty_roles` | C-AUTH-03 |
| `test_keycloak_mode_fetches_jwks` | C-AUTH-04 |
| `test_jwks_cached_for_ttl` | C-AUTH-04, FR-017 |
| `test_jwks_refreshed_after_ttl_expired` | C-AUTH-04, FR-017 |
| `test_algorithm_confusion_rejected` | BLK-01 (security) |
| `test_unrecognised_auth_mode_raises` | BLK-03 (security) |
| `test_startup_fails_if_jwks_unreachable` | BLK-02, FR-015 (security) |

**`test_keycloak_client.py`** — 6 tests × 3 services (orchestrator, agent-dispatcher, UIM) = 18 tests

| Test | Requirement |
|------|-------------|
| `test_get_token_calls_keycloak_token_endpoint` | C-KC-01 |
| `test_token_cached_until_expiry` | C-KC-01, SC-006 |
| `test_token_refreshed_30s_before_expiry` | C-KC-01 |
| `test_concurrent_calls_use_single_request` | C-KC-02, US3-AC4 |
| `test_keycloak_error_raises_upstream_error` | C-KC-03 |
| `test_client_secret_not_in_upstream_error` | FIND-01 (security) |

**Total unit tests written**: 84

### Frontend Tests (frontend agent — Vitest)

- `authStore.test.ts` — mock keycloak-js, spy on localStorage/sessionStorage (FIND-02)
- `LoadingScreen.test.tsx` — renders while `!initialized`; disappears after initialize()
- Required by security review: `test_localStorage_never_written`, `test_sessionStorage_never_written`

### Integration Tests (future — against running Keycloak)

Scenarios from `specs/004-keycloak-iam-migration/quickstart.md`:

| Scenario | Acceptance Criteria | Auth Mode |
|----------|---------------------|-----------|
| 1. SSO login, cross-app session | US1-AC1, US1-AC2, FR-001, FR-002 | AUTH_MODE=keycloak |
| 2. API call with valid Bearer | SC-002, FR-016 | AUTH_MODE=keycloak |
| 3. Admin link appears for admin role | US2-AC2, FR-005 | AUTH_MODE=keycloak |
| 4. Service-to-service CC token | US3-AC1, FR-007 | AUTH_MODE=keycloak |
| 5. Agent token injection | US3-AC2, FR-009 | AUTH_MODE=keycloak |
| 6. Data integrity after migration | US4-AC1, FR-012 | AUTH_MODE=keycloak |
| 7. Full test suite with invalid API key | SC-004 | AUTH_MODE=local |
| 8. Logout clears session | US1-AC3, FR-018 | AUTH_MODE=keycloak |

---

## AUTH_MODE=local Test Harness

All automated CI tests use `AUTH_MODE=local` with HS256 and `TEST_JWT_SECRET`. No real Keycloak required.

**Fixture contract** (per `conftest.py` per service after T019-T024):

```python
@pytest.fixture
def user_token() -> str:
    # HS256, realm_access.roles=["user"]

@pytest.fixture  
def admin_token() -> str:
    # HS256, realm_access.roles=["user","administrator"]

@pytest.fixture(autouse=True)
def set_auth_mode(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", "test-secret-do-not-use-in-production")
```

**Dependency**: T019-T024 (conftest.py rewrites) must be complete before test runs.

---

## CI Requirements

### On Every Commit/PR

```bash
# Per service (example for UIM):
cd services/user-input-manager/backend
pytest tests/unit/ -x --tb=short

# All services:
for svc in services/*/backend services/orchestrator services/context-distiller services/agent-dispatcher services/agent-tools; do
  pytest $svc/tests/unit/ --tb=short
done
```

### Security Gate (CI, T079 scope)

```bash
# BLK-03: AUTH_MODE=local must not appear in docker-compose.yml
grep -r 'AUTH_MODE=local' infra/docker-compose.yml && exit 1 || true
grep -r 'test-secret-do-not-use-in-production' infra/docker-compose.yml && exit 1 || true
```

### Regression Suite

All per-service `tests/unit/` suites must pass with no changes after the migration. Existing tests for business logic (FSM, planners, reporters) must remain green — they are not auth-aware.

---

## Acceptance Criteria Coverage

| Criterion | Test Method | Status |
|-----------|------------|--------|
| SC-001 (login < 5s) | Manual / E2E | Not automated |
| SC-002 (all endpoints accept KC tokens) | Integration test Scenario 2 | Pending |
| SC-003 (no passwords in DB) | SQL query post-migration | Pending |
| SC-004 (CI tests pass with local mode) | Unit tests / AUTH_MODE=local | ✅ Written |
| SC-005 (admin lifecycle < 3min) | Manual | Not automated |
| SC-006 (CC token ≤200ms on cache miss) | Performance test | Pending |
| SC-007 (migration preserves data) | Integration test Scenario 6 | Pending |
| SC-008 (no token in logs) | Log audit / unit test for FIND-01 | ✅ test_client_secret_not_in_upstream_error |
| BLK-01 (alg pinning) | test_algorithm_confusion_rejected | ✅ Written |
| BLK-02 (startup fail-closed) | test_startup_fails_if_jwks_unreachable | ✅ Written |
| BLK-03 (no local in compose) | CI grep check | To be added by DevOps |
| FR-015 (service won't start without KC) | test_startup_fails_if_jwks_unreachable | ✅ Written |
| FR-017 (JWKS ≥300s cache) | test_jwks_cached_for_ttl | ✅ Written |
| FR-018 (tokens in memory only) | Frontend authStore.test.ts | Pending (frontend) |

---

## Untested Areas

- **E2E / SSO flows**: require running Keycloak — deferred to manual quickstart verification (T081)
- **SC-001 login latency**: not measurable in unit tests
- **SC-006 token fetch latency**: needs performance test in staging
- **Disabled-account token rejection (US1-AC4)**: requires Keycloak admin API — manual only
- **Google IdP placeholder**: tested by verifying `enabled: false` in realm-export.json — no automated test
- **Data migration integrity (US4)**: requires a populated database — integration test against throwaway DB

---

## Release Recommendation

**Status**: NOT YET EVALUATED — Phase 2 backend implementation not yet complete.

Unit test files written and ready. Final recommendation will be issued after:
1. Phase 2 (T007-T024) is complete and tests run green
2. Phase 3-7 acceptance criteria verified via integration tests
3. Security blockers BLK-01/02/03 confirmed addressed in code

---

## Follow-Up Items

- [ ] Coordinate with backend agent: confirm `KeycloakValidator._fetch_jwks()` is a public method so `test_startup_fails_if_jwks_unreachable` can call it directly, OR expose it via a FastAPI startup event that tests can exercise
- [ ] Coordinate with frontend agent: add `test_localStorage_never_written` and `test_sessionStorage_never_written` Vitest tests to both `authStore.test.ts` files (FIND-02)
- [ ] Coordinate with devops: confirm CI grep check for `AUTH_MODE=local` in docker-compose.yml is added (BLK-03)
- [ ] Add integration test for `require_admin` returning 403 for user-role tokens once backend Phase 4 complete
