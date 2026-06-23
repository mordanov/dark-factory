# Quickstart: Project Groups, Assignee-Only Transitions, and Tokens Spent

**Feature**: `006-project-groups-transitions-tokens` | **Date**: 2026-06-23

## Prerequisites

- Docker and Docker Compose installed
- `infra/.env` filled (copy from `infra/.env.example`; set `POSTGRES_PASSWORD`, `SECRET_KEY`)
- Monorepo root: `dark-factory/`

## Run as Part of the Monorepo

```bash
# Start everything (first time will build images)
docker compose -f infra/docker-compose.yml up --build

# Apply ticket-manager DB migrations
docker compose -f infra/docker-compose.yml exec ticket-manager \
  alembic upgrade head
```

## Run ticket-manager in Isolation

```bash
cd services/ticket-manager/backend

# Start with standalone compose (includes local postgres)
docker compose up --build

# Apply migrations
docker compose exec backend alembic upgrade head
```

## Run Backend Tests

```bash
cd services/ticket-manager/backend
pytest --cov=src --cov-report=term-missing -q
```

Coverage target: ≥ 80% lines and functions.

```bash
# Specific feature tests
pytest tests/contract/test_groups.py tests/contract/test_tokens_spent.py -q
pytest tests/integration/test_project_group_service.py \
       tests/integration/test_transition_no_gate.py \
       tests/integration/test_tokens_spent_service.py -q
```

## Run Frontend Tests

```bash
cd services/ticket-manager/frontend
npm run test -- --run    # CI mode
npm run coverage
```

## New Environment Variables

No new environment variables are required for this feature. All changes use the existing
`DATABASE_URL`, `SECRET_KEY`, and auth configuration.

## Manual End-to-End Walkthrough

### US1 — Project Groups

1. **Login**: `POST /auth/login` → get `access_token`

2. **Create a group**:
   ```bash
   curl -X POST http://localhost:8002/api/v1/groups \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"identifier": "TEAM1", "name": "Team Alpha"}'
   # Returns 201 with group details including UUID
   ```

3. **List groups**:
   ```bash
   curl http://localhost:8002/api/v1/groups \
     -H "Authorization: Bearer <token>"
   # Shows DEFAULT + TEAM1
   ```

4. **Create project in group**:
   ```bash
   curl -X POST http://localhost:8002/api/v1/projects \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"name": "Alpha Project", "group_id": "<TEAM1_group_uuid>"}'
   ```

5. **Create project without group** (auto-assigned to DEFAULT):
   ```bash
   curl -X POST http://localhost:8002/api/v1/projects \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"name": "Ungrouped Project"}'
   # group field in response will show DEFAULT
   ```

6. **Filter projects by group**:
   ```bash
   curl "http://localhost:8002/api/v1/projects?group_id=<TEAM1_group_uuid>" \
     -H "Authorization: Bearer <token>"
   # Returns only projects in TEAM1
   ```

7. **Move project to another group**:
   ```bash
   curl -X PATCH http://localhost:8002/api/v1/projects/<project_uuid> \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"group_id": "<DEFAULT_group_uuid>"}'
   ```

8. **Try to delete DEFAULT group** (should fail):
   ```bash
   curl -X DELETE http://localhost:8002/api/v1/groups/<DEFAULT_group_uuid> \
     -H "Authorization: Bearer <token>"
   # Returns 409 Conflict
   ```

### US2 — Assignee-Only Transitions

1. Create a ticket and assign User A to it.
2. As User A (assignee), transition the ticket **without submitting a progress update**:
   ```bash
   curl -X POST http://localhost:8002/api/v1/tickets/<ticket_uuid>/transitions \
     -H "Authorization: Bearer <userA_token>" \
     -H "Content-Type: application/json" \
     -d '{"to_status": "IN_PROGRESS"}'
   # Returns 200 immediately — no 422 about missing progress updates
   ```

3. As User B (non-assignee), attempt the same transition:
   ```bash
   curl -X POST http://localhost:8002/api/v1/tickets/<ticket_uuid>/transitions \
     -H "Authorization: Bearer <userB_token>" \
     -H "Content-Type: application/json" \
     -d '{"to_status": "IN_REVIEW"}'
   # Returns 403 Forbidden
   ```

### US3 — Tokens Spent

1. Increment tokens spent:
   ```bash
   curl -X POST http://localhost:8002/api/v1/tickets/<ticket_uuid>/tokens-spent \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"amount": 500}'
   # Returns: { "ticket_id": "...", "tokens_spent": 500, "amount_added": 500, "event_id": "..." }
   ```

2. Increment again:
   ```bash
   curl -X POST http://localhost:8002/api/v1/tickets/<ticket_uuid>/tokens-spent \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"amount": 200}'
   # Returns: { "tokens_spent": 700, "amount_added": 200, ... }
   ```

3. View token history in ticket events:
   ```bash
   curl http://localhost:8002/api/v1/tickets/<ticket_uuid>/events \
     -H "Authorization: Bearer <token>"
   # Shows "ticket.tokens_spent_incremented" events for each increment
   ```

4. Try to use amount=0 or negative (should fail):
   ```bash
   curl -X POST http://localhost:8002/api/v1/tickets/<ticket_uuid>/tokens-spent \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"amount": -10}'
   # Returns 422 Unprocessable
   ```

5. Verify total on ticket detail:
   ```bash
   curl http://localhost:8002/api/v1/tickets/<ticket_uuid> \
     -H "Authorization: Bearer <token>"
   # Response includes "tokens_spent": 700 and "tokens_consumed": <system value>
   ```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Migration 017 fails on `NOT NULL` alter | Existing projects have null group_id after backfill attempt | Check that DEFAULT group insert succeeded before backfill; run migration step by step in psql |
| `POST /api/v1/groups` returns 409 on first run | DEFAULT group seed was already applied by a prior migration run | Safe to ignore; DEFAULT exists |
| `DELETE /api/v1/groups/<id>` returns 409 unexpectedly | Group has projects linked to it | Use `GET /api/v1/groups/<id>` to check `project_count`; move projects first |
| Transition returns 403 after adding assignee | Auth token belongs to non-assignee | Verify correct user token; use `GET /api/v1/tickets/<id>` to see `assignees[]` |
| `POST .../tokens-spent` returns 422 | `amount` is 0 or negative | Amount must be a positive integer ≥1 |
| `tokens_spent` shows 0 after increment | Stale cache in frontend | Invalidate React Query cache for ticket; check response from POST endpoint directly |
