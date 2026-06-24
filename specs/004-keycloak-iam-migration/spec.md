# Feature Specification: Keycloak IAM Migration

**Feature Branch**: `004-keycloak-iam-migration`
**Created**: 2026-06-24
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Unified Single Sign-On for All Users (Priority: P1)

Any person with a Dark Factory account can log in once through a single identity provider and immediately access all services (Prompt Studio and Ticket Manager) without re-entering credentials. Login happens via browser redirect; no separate per-application login screen exists.

**Why this priority**: This is the foundational change. Without a working SSO login flow, no other part of the migration can be validated end-to-end. All downstream stories depend on identity being established at the boundary.

**Independent Test**: A new user account created in the identity management console can log into both frontends and receive a valid session. A user whose account is disabled is immediately denied access on next request.

**Acceptance Scenarios**:

1. **Given** a user with a valid account exists, **When** they open either frontend for the first time, **Then** they are redirected to the identity provider login page and, upon successful authentication, returned to the application fully logged in.
2. **Given** a logged-in user, **When** they open the second frontend application (without logging in again), **Then** they are immediately authenticated without seeing a login prompt.
3. **Given** a logged-in user, **When** they click "Logout", **Then** their session is terminated and they are redirected to the login page; subsequent navigation to any protected page requires re-authentication.
4. **Given** a user whose account has been disabled by an administrator, **When** their current session token expires, **Then** they cannot obtain a new session and are redirected to login.
5. **Given** a user attempts to log in with incorrect credentials, **When** the login form is submitted, **Then** an appropriate error message is shown and access is denied.

---

### User Story 2 — Administrator Manages Users via Identity Console (Priority: P2)

Administrators manage all user accounts — create, enable/disable, reset passwords, and assign roles — exclusively through the dedicated identity management console. The application itself no longer contains any user management screens.

**Why this priority**: User management is a critical operational capability. Administrators need a working path to onboard new users, respond to security incidents (disable accounts), and control role assignments. Removing the old admin UI without providing this path would block operations.

**Independent Test**: An administrator can create a new user in the identity console, assign the "administrator" role, and verify that user can log into the application with elevated privileges. Disabling a user in the console prevents future logins.

**Acceptance Scenarios**:

1. **Given** an administrator is logged into the identity management console, **When** they create a new user and assign the "user" role, **Then** that user can log into all Dark Factory frontends.
2. **Given** a user has the "administrator" role, **When** they log into the application, **Then** they see a link to the identity management console in the sidebar; users without the role do not see this link.
3. **Given** an administrator disables a user account in the console, **When** that user's current token expires, **Then** token refresh is rejected and the user must re-authenticate (which fails because the account is disabled).
4. **Given** a user needs a password reset, **When** an administrator triggers a reset in the console, **Then** the user receives a temporary credential and is prompted to change it on next login.
5. **Given** the application is running, **When** an administrator navigates to the old admin user management URL, **Then** the route no longer exists and they are redirected to the main application.

---

### User Story 3 — Services Authenticate Inter-Service Calls Without User Credentials (Priority: P3)

Backend services that call other services (e.g., Orchestrator calling Ticket Manager, Agent Dispatcher injecting tokens for agents) authenticate using machine-to-machine credentials issued by the identity provider. No service stores, generates, or forwards user passwords. Agents receive a short-lived access token at spawn time.

**Why this priority**: Without secure service-to-service authentication, automated workflows (agent runs, context collection, reporting) break. This unblocks the entire agent pipeline and removes the current shared-secret anti-pattern.

**Independent Test**: An orchestrator workflow can call the Ticket Manager API and receive a valid response without any user being logged in. An agent receives a token at spawn time and can call the Ticket Manager API for the duration of its run.

**Acceptance Scenarios**:

1. **Given** the Orchestrator needs to create a ticket on behalf of a workflow, **When** it calls the Ticket Manager API, **Then** the call succeeds using machine credentials (not a user's token) and the response includes the created ticket.
2. **Given** the Agent Dispatcher spawns an agent, **When** the agent context is built, **Then** a valid access token is injected into the agent's context for use with Dark Factory APIs; the token is valid for at least 1 hour.
3. **Given** a service-to-service credential is revoked in the identity console, **When** the affected service attempts to obtain a new token, **Then** the call fails and the service reports an authentication error rather than silently continuing.
4. **Given** multiple services are running simultaneously, **When** each calls the identity provider for a token, **Then** all receive valid tokens concurrently without deadlock or race conditions.

---

### User Story 4 — All Existing Data and Workflows Remain Intact After Migration (Priority: P4)

All existing tickets, projects, sessions, and agent runs survive the migration. The destructive change is limited to user identity records (which move to the identity provider). All business data referenced by a user's identity is re-linked to the new identity format automatically.

**Why this priority**: Operational continuity. A migration that destroys business data is unacceptable. This story validates that the schema migration approach preserves all non-identity data.

**Independent Test**: After migration, an existing project and all its tickets are accessible via the API. A user logged in with their new identity can see the same tickets and projects they created before the migration (assuming user IDs are mapped or data is seeded appropriately in the test environment).

**Acceptance Scenarios**:

1. **Given** the migration runs against a database with existing tickets, **When** the migration completes, **Then** all tickets, projects, and events remain present and queryable via the API.
2. **Given** a ticket was created by a user who previously had a local account, **When** that ticket is retrieved via the API after migration, **Then** the `created_by` and `assignee` fields reflect the migrated identity reference.
3. **Given** the migration is destructive (user table dropped), **When** the migration is applied, **Then** no rollback path is available, and the migration log confirms the irreversible nature.

---

### Edge Cases

- What happens when the identity provider is unavailable at service startup? Services must fail to start (not start in a degraded mode accepting any token).
- What happens when the identity provider becomes unavailable while services are already running? Services continue serving requests using the cached public key material until the cache TTL expires (minimum 5 minutes). Each failed refresh attempt is logged as a warning. Once the cache expires without a successful refresh, new token validations begin failing with a 503 error until the identity provider is reachable again.
- What happens when a token expires mid-request? The request must return a 401; the client refreshes the token automatically and retries.
- What happens when Google login is enabled in the identity provider but the user's Google account email doesn't match an existing account? A new account is created in the identity provider on first login.
- What happens if a service's machine credential secret is leaked? The secret can be rotated in the identity console without redeploying the service (via environment variable update and restart).
- What happens when a new service is added to the system? It must obtain its own machine credential from the identity provider before it can call other services.
- What happens when a user has the same email in both local accounts and a Google-linked account? The identity provider's duplicate email prevention rejects the second registration.

## Clarifications

### Session 2026-06-24

- Q: When Keycloak becomes unavailable at runtime (services already running), should services use the stale JWKS cache or fail immediately? → A: Continue using stale JWKS cache for the remainder of the cached TTL, log a warning on each failed refresh; begin failing new token validations with 503 only after the cache expires without a successful refresh.
- Q: Implementation team structure — which agent coordinates and how is work split across the 10-agent team? → A: Default split. product-manager coordinates. devops owns infra files (T001–T006). backend owns all 6 backend auth adapter rewrites, config changes, and KeycloakServiceClient. frontend owns both frontend keycloak-js streams. security-architect reviews all auth contracts before code ships. autotester writes unit tests. code-reviewer does final pass.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST redirect unauthenticated users to a centralized login page when they attempt to access any protected resource.
- **FR-002**: The system MUST support SSO across all frontend applications — a session established in one application MUST be recognized by all others.
- **FR-003**: The system MUST invalidate all active sessions for a user when an administrator disables that user's account.
- **FR-004**: Administrators MUST be able to create, enable, disable, and delete user accounts through the identity management console without modifying application configuration.
- **FR-005**: Administrators MUST be able to assign and revoke the "administrator" role to any user account.
- **FR-006**: The system MUST support password reset initiated by an administrator, delivering temporary credentials to the user.
- **FR-007**: Backend services MUST authenticate inter-service API calls using machine-to-machine credentials; no service may use a user's token to call another service on its own behalf.
- **FR-008**: Machine credentials MUST be independently revocable per service without affecting other services.
- **FR-009**: Agents spawned by the Agent Dispatcher MUST receive a short-lived access token at spawn time, valid for at least 1 hour.
- **FR-010**: The system MUST remove all local user management endpoints from application APIs (registration, login, user CRUD, session management).
- **FR-011**: The system MUST remove the admin user management screen from all frontend applications.
- **FR-012**: All existing business data (tickets, projects, sessions, agent runs, events) MUST be preserved after migration; only user identity records are replaced.
- **FR-013**: The database schema migration that removes the local user table MUST be irreversible (no rollback path).
- **FR-014**: The identity provider MUST have Google login configured in the realm definition, disabled by default, and enableable without application redeployment.
- **FR-015**: All services MUST enforce that the identity provider is healthy before accepting requests; a service MUST NOT start accepting traffic if it cannot reach the identity provider.
- **FR-016**: Identity tokens MUST be validated using public key cryptography; no service may rely on a shared secret for validating user identity tokens in production.
- **FR-017**: Token validation public keys MUST be cached for a minimum of 5 minutes to avoid per-request lookups. If the identity provider is unreachable during a cache refresh, the stale cache MUST continue to be used until it expires, with a warning logged on each failed refresh attempt. Once the cache expires without a successful refresh, new token validations MUST return a 503 error until the identity provider is reachable again.
- **FR-018**: Frontend applications MUST store access tokens in memory only — never in browser storage (localStorage, sessionStorage, cookies accessible to JavaScript).
- **FR-019**: The system MUST surface a "Connecting…" loading screen to users while the identity provider session is being established on app load; no application content is visible until authentication is confirmed.

### Key Entities

- **Realm**: The top-level logical grouping for all Dark Factory identity configuration. Fixed name. Contains all users, roles, and client registrations.
- **User**: A human identity managed entirely by the identity provider. Attributes: username, email, enabled status, realm roles. No longer stored in application databases.
- **Role**: A coarse-grained access level assigned to users (e.g., "user", "administrator"). Used by applications to show/hide features and gate admin operations.
- **Service Client**: A machine identity representing a backend service. Used for service-to-service calls. Has its own credential (secret) and token lifetime.
- **Frontend Client**: A public client registration for a browser application. Uses PKCE for secure token exchange. No client secret.
- **Access Token**: A short-lived, signed credential issued to a user or service after successful authentication. Contains identity claims and role assignments.
- **User Identity Reference**: The opaque identifier (the identity provider's subject claim) stored in application database records in place of the old user table foreign key.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can log in to either frontend and reach their first screen in under 5 seconds from credential submission (excluding network latency to the identity provider).
- **SC-002**: 100% of application API endpoints that previously required a local JWT now accept identity provider tokens and reject requests with invalid or expired tokens.
- **SC-003**: Zero user passwords are stored in any application database after the migration is applied.
- **SC-004**: All automated integration tests that cover authentication pass using the local test mode (no real identity provider required for CI runs).
- **SC-005**: An administrator can complete the full user lifecycle (create → assign role → disable → re-enable) in under 3 minutes using only the identity console.
- **SC-006**: Service-to-service calls succeed within existing p95 latency budgets — the added token fetch step adds no more than 200ms on a cache miss, and zero overhead on a cache hit.
- **SC-007**: The migration script completes without data loss: all ticket, project, session, and event records present before migration are present after migration.
- **SC-008**: No application stores or logs access token values in plaintext; audit logging records identity subject claims only.

## Assumptions

- The identity provider runs as a containerized service alongside all other Dark Factory services; no external identity-as-a-service is used.
- The "dark-factory" realm name is fixed and cannot be changed post-deployment without a full re-configuration.
- Self-registration (users creating their own accounts) is disabled; only administrators can create accounts.
- There is no requirement to migrate existing user passwords into the identity provider — the migration is a fresh start for identity; existing users will be re-provisioned manually.
- Google login is a future capability; it is included in the configuration but disabled by default at deployment.
- MFA configuration, custom login themes, and Keycloak high-availability clustering are out of scope for this migration.
- The identity provider's admin console is accessible on the internal network only; it is not exposed via the public-facing nginx proxy.
- All Dark Factory services communicate over a trusted internal Docker network; TLS between services on this network is not required (TLS terminates at nginx).
- The agent dispatcher's machine credential has a longer token lifetime (1 hour) because agents are long-running and cannot refresh tokens interactively.
- Per-application roles (scoped permissions beyond "user" and "administrator") are out of scope; all role checks are on global realm roles only.
- User data migration (mapping old integer/UUID user IDs to identity provider subject claims) is out of scope; the application operates on fresh identity post-migration and historical `created_by`/`assignee` fields store the identity provider subject string.
