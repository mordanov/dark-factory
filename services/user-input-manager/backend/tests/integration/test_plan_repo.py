"""Integration tests for src.repositories.plan_repo — PlanRepository."""

import uuid

import pytest
import pytest_asyncio
from src.core.security import hash_password
from src.models.models import PromptPlan, PromptSession, User
from src.repositories.plan_repo import PlanRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_PLAN_DICT = {
    "epic": {
        "local_id": "epic-1",
        "title": "Build auth system",
        "description": "Implement JWT authentication",
        "ticket_type": "epic",
    },
    "stories": [
        {
            "local_id": "story-1",
            "title": "Backend auth",
            "description": "JWT service and endpoints",
            "ticket_type": "story",
            "tasks": [
                {
                    "local_id": "task-1-1",
                    "title": "Create JWT service",
                    "description": "Token gen and validation",
                    "ticket_type": "task",
                    "complexity": "M",
                    "depends_on": [],
                },
                {
                    "local_id": "task-1-2",
                    "title": "Add login endpoint",
                    "description": "POST /auth/login",
                    "ticket_type": "task",
                    "complexity": "S",
                    "depends_on": ["task-1-1"],
                },
            ],
        }
    ],
}


@pytest_asyncio.fixture
async def plan_test_user(db):
    """Isolated user for plan repo tests — unique email to avoid conftest user collisions."""
    unique = str(uuid.uuid4())[:8]
    user = User(
        email=f"plan-test-{unique}@test.com",
        password_hash=hash_password("Test1234!"),
        full_name="Plan Test User",
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def session_for_plan(db, plan_test_user):
    session = PromptSession(
        user_id=plan_test_user.id,
        session_type="new_project",
        tm_project_name="Repo Test Project",
        tm_project_id="proj-repo-test",
        status="approved",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture
async def repo(db):
    return PlanRepository(db)


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_plan_with_content(repo, session_for_plan):
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    assert plan.id is not None
    assert plan.session_id == session_for_plan.id
    assert plan.status == "draft"
    assert plan.plan_content["epic"]["title"] == "Build auth system"


@pytest.mark.asyncio
async def test_create_plan_without_content(repo, session_for_plan):
    plan = await repo.create(session_id=session_for_plan.id)
    assert plan.id is not None
    assert plan.plan_content is None
    assert plan.agent_config is None


@pytest.mark.asyncio
async def test_create_plan_with_agent_config(repo, session_for_plan):
    agent_cfg = {"project_id": "proj-1", "tech_stack": ["Python"], "agent_overrides": []}
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
        agent_config=agent_cfg,
    )
    assert plan.agent_config["project_id"] == "proj-1"


# ---------------------------------------------------------------------------
# get_by_session_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_session_id_returns_plan(repo, session_for_plan):
    created = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    fetched = await repo.get_by_session_id(session_for_plan.id)
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_by_session_id_returns_none_when_not_found(repo):
    result = await repo.get_by_session_id(uuid.uuid4())
    assert result is None


# ---------------------------------------------------------------------------
# update_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_content_replaces_plan_dict(repo, session_for_plan):
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    new_content = {
        **VALID_PLAN_DICT,
        "epic": {**VALID_PLAN_DICT["epic"], "title": "Updated epic title"},
    }
    updated = await repo.update_content(plan, new_content)
    assert updated.plan_content["epic"]["title"] == "Updated epic title"


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_changes_plan_status(repo, session_for_plan):
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    updated = await repo.update_status(plan, "ready")
    assert updated.status == "ready"


@pytest.mark.asyncio
async def test_update_status_with_extra_kwargs(repo, session_for_plan):
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    updated = await repo.update_status(plan, "tickets_created", tm_epic_id="tm-epic-99")
    assert updated.status == "tickets_created"
    assert updated.tm_epic_id == "tm-epic-99"


@pytest.mark.asyncio
async def test_update_status_sets_error_state(repo, session_for_plan):
    plan = await repo.create(session_id=session_for_plan.id)
    updated = await repo.update_status(
        plan,
        "error",
        validation_errors=["Ticket creation timed out"],
    )
    assert updated.status == "error"
    assert "Ticket creation timed out" in updated.validation_errors


# ---------------------------------------------------------------------------
# append_created_ticket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_created_ticket_adds_to_map(repo, session_for_plan):
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    updated = await repo.append_created_ticket(plan, "task-1-1", "tm-task-abc")
    assert updated.ticket_id_map == {"task-1-1": "tm-task-abc"}
    assert "tm-task-abc" in updated.created_ticket_ids


@pytest.mark.asyncio
async def test_append_created_ticket_accumulates_multiple(repo, session_for_plan):
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    plan = await repo.append_created_ticket(plan, "epic-1", "tm-epic-1")
    plan = await repo.append_created_ticket(plan, "story-1", "tm-story-1")
    plan = await repo.append_created_ticket(plan, "task-1-1", "tm-task-1")

    assert len(plan.created_ticket_ids) == 3
    assert plan.ticket_id_map == {
        "epic-1": "tm-epic-1",
        "story-1": "tm-story-1",
        "task-1-1": "tm-task-1",
    }


@pytest.mark.asyncio
async def test_append_created_ticket_is_idempotent_for_same_local_id(repo, session_for_plan):
    """Calling append_created_ticket twice with the same local_id must not duplicate."""
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    plan = await repo.append_created_ticket(plan, "task-1-1", "tm-task-abc")
    plan = await repo.append_created_ticket(plan, "task-1-1", "tm-task-abc")

    assert plan.ticket_id_map["task-1-1"] == "tm-task-abc"
    # created_ticket_ids must not have duplicate TM IDs
    assert plan.created_ticket_ids.count("tm-task-abc") == 1


@pytest.mark.asyncio
async def test_append_created_ticket_updates_existing_map_entry(repo, session_for_plan):
    """If same local_id is re-mapped to a new TM id (retry), the map is updated."""
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    plan = await repo.append_created_ticket(plan, "task-1-1", "tm-task-v1")
    plan = await repo.append_created_ticket(plan, "task-1-1", "tm-task-v1")

    # Map still points to same tm id, no duplicates
    assert list(plan.created_ticket_ids).count("tm-task-v1") == 1


# ---------------------------------------------------------------------------
# Persistence: get_by_session_id reflects mutations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_session_id_reflects_status_update(repo, session_for_plan):
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    await repo.update_status(plan, "confirmed")
    fetched = await repo.get_by_session_id(session_for_plan.id)
    assert fetched.status == "confirmed"


@pytest.mark.asyncio
async def test_get_by_session_id_reflects_ticket_append(repo, session_for_plan):
    plan = await repo.create(
        session_id=session_for_plan.id,
        plan_content=VALID_PLAN_DICT,
    )
    await repo.append_created_ticket(plan, "epic-1", "tm-epic-x")
    fetched = await repo.get_by_session_id(session_for_plan.id)
    assert fetched.ticket_id_map["epic-1"] == "tm-epic-x"


# ---------------------------------------------------------------------------
# delete_by_session_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_by_session_id_removes_plan(repo, session_for_plan):
    await repo.create(session_id=session_for_plan.id, plan_content=VALID_PLAN_DICT)
    await repo.delete_by_session_id(session_for_plan.id)
    assert await repo.get_by_session_id(session_for_plan.id) is None


@pytest.mark.asyncio
async def test_delete_by_session_id_is_noop_when_no_plan(repo, session_for_plan):
    # Should not raise even when no plan exists
    await repo.delete_by_session_id(session_for_plan.id)
