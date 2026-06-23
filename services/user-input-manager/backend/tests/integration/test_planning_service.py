"""Integration tests for PlanningService."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks
from src.core.exceptions import ConflictError, NotFoundError, UpstreamError
from src.core.security import hash_password
from src.models.models import PromptPlan, PromptSession, User
from src.repositories.plan_repo import PlanRepository
from src.repositories.session_repo import SessionRepository
from src.schemas.schemas import PlanContent
from src.services.planning_service import PlanningService


@pytest_asyncio.fixture
async def svc_user(db):
    """Isolated user for planning service tests — unique email per run."""
    unique = str(uuid.uuid4())[:8]
    user = User(
        email=f"svc-test-{unique}@test.com",
        password_hash=hash_password("Test1234!"),
        full_name="Svc Test User",
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


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
            "description": "JWT service",
            "ticket_type": "story",
            "tasks": [
                {
                    "local_id": "task-1-1",
                    "title": "JWT service",
                    "description": "Generate/validate tokens",
                    "ticket_type": "task",
                    "complexity": "M",
                    "depends_on": [],
                },
                {
                    "local_id": "task-1-2",
                    "title": "Auth endpoints",
                    "description": "Login/refresh",
                    "ticket_type": "task",
                    "complexity": "S",
                    "depends_on": ["task-1-1"],
                },
            ],
        }
    ],
}


@pytest_asyncio.fixture
async def approved_session(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="Test Project",
        tm_project_id="proj-test",
        status="approved",
    )
    db.add(session)

    from src.models.models import PromptIteration
    iter1 = PromptIteration(
        session_id=None,
        iteration_number=1,
        role="assistant",
        prompt_text="Build an authentication system with JWT",
    )
    db.add(session)
    await db.flush()
    iter1.session_id = session.id
    db.add(iter1)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture
async def ready_plan(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="Test Project",
        tm_project_id="proj-test-2",
        status="plan_ready",
    )
    db.add(session)
    await db.flush()

    plan = PromptPlan(
        session_id=session.id,
        status="ready",
        plan_content=VALID_PLAN_DICT,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(session)
    await db.refresh(plan)
    return session, plan


def _mock_tm_client(epic_id="tm-epic-1", story_id="tm-story-1", task_id="tm-task-1"):
    client = MagicMock()
    client.create_epic = AsyncMock(return_value=epic_id)
    client.create_story = AsyncMock(return_value=story_id)
    client.create_task = AsyncMock(return_value=task_id)
    return client


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_transitions_session_to_plan_ready(db, approved_session, svc_user):
    plan_content = PlanContent.model_validate(VALID_PLAN_DICT)
    tm = _mock_tm_client()

    with (
        patch("src.services.planning_service.generate_plan", return_value=plan_content),
        patch("src.services.planning_service.generate_agent_config", return_value=None),
    ):
        svc = PlanningService(db, tm)
        response = await svc.generate(approved_session.id, svc_user.id)

    assert response.session_id == approved_session.id
    repo = PlanRepository(db)
    plan = await repo.get_by_session_id(approved_session.id)
    assert plan is not None
    assert plan.status == "ready"

    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(approved_session.id)
    assert session.status == "plan_ready"


@pytest.mark.asyncio
async def test_generate_resets_session_on_llm_failure(db, approved_session, svc_user):
    tm = _mock_tm_client()

    with patch(
        "src.services.planning_service.generate_plan",
        side_effect=UpstreamError("LLM down"),
    ):
        svc = PlanningService(db, tm)
        with pytest.raises(UpstreamError):
            await svc.generate(approved_session.id, svc_user.id)

    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(approved_session.id)
    assert session.status == "approved"


@pytest.mark.asyncio
async def test_generate_raises_conflict_if_not_approved(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="X",
        status="in_progress",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    tm = _mock_tm_client()
    svc = PlanningService(db, tm)
    with pytest.raises(ConflictError):
        await svc.generate(session.id, svc_user.id)


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_saves_new_content(db, ready_plan, svc_user):
    session, plan = ready_plan
    tm = _mock_tm_client()
    svc = PlanningService(db, tm)

    new_content = dict(VALID_PLAN_DICT)
    new_content["epic"] = dict(VALID_PLAN_DICT["epic"], title="Updated Epic Title")
    result = await svc.update(session.id, svc_user.id, new_content)

    assert result.plan_content["epic"]["title"] == "Updated Epic Title"


@pytest.mark.asyncio
async def test_update_raises_conflict_if_plan_confirmed(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="X",
        tm_project_id="proj-x",
        status="plan_confirmed",
    )
    db.add(session)
    await db.flush()
    plan = PromptPlan(session_id=session.id, status="confirmed", plan_content=VALID_PLAN_DICT)
    db.add(plan)
    await db.commit()

    tm = _mock_tm_client()
    svc = PlanningService(db, tm)
    with pytest.raises(ConflictError):
        await svc.update(session.id, svc_user.id, VALID_PLAN_DICT)


# ---------------------------------------------------------------------------
# confirm() — gate: returns 202, no TM calls during request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_returns_immediately_without_tm_calls(db, ready_plan, svc_user):
    session, plan = ready_plan
    tm = _mock_tm_client()
    bg = BackgroundTasks()
    svc = PlanningService(db, tm)

    result = await svc.confirm(session.id, svc_user.id, bg)

    assert result.status == "confirmed"
    # No TM calls made synchronously
    tm.create_epic.assert_not_called()
    tm.create_story.assert_not_called()
    tm.create_task.assert_not_called()

    repo = PlanRepository(db)
    updated_plan = await repo.get_by_session_id(session.id)
    assert updated_plan.status == "confirmed"

    session_repo = SessionRepository(db)
    updated_session = await session_repo.get_by_id(session.id)
    assert updated_session.status == "plan_confirmed"


@pytest.mark.asyncio
async def test_confirm_raises_conflict_if_not_ready(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="X",
        tm_project_id="proj-x",
        status="plan_confirmed",
    )
    db.add(session)
    await db.flush()
    plan = PromptPlan(session_id=session.id, status="confirmed", plan_content=VALID_PLAN_DICT)
    db.add(plan)
    await db.commit()

    tm = _mock_tm_client()
    svc = PlanningService(db, tm)
    with pytest.raises(ConflictError):
        await svc.confirm(session.id, svc_user.id, BackgroundTasks())


# ---------------------------------------------------------------------------
# _create_tickets() — full happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tickets_full_success(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="TM Project",
        tm_project_id="proj-full",
        status="plan_confirmed",
    )
    db.add(session)
    await db.flush()
    plan = PromptPlan(
        session_id=session.id,
        status="confirmed",
        plan_content=VALID_PLAN_DICT,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    call_count = {"story": 0, "task": 0}

    async def mock_create_story(project_id, story, epic_tm_id):
        call_count["story"] += 1
        return f"tm-story-{call_count['story']}"

    async def mock_create_task(project_id, task, story_tm_id, dep_tm_ids):
        call_count["task"] += 1
        return f"tm-task-{call_count['task']}"

    tm = MagicMock()
    tm.create_epic = AsyncMock(return_value="tm-epic-1")
    tm.create_story = AsyncMock(side_effect=mock_create_story)
    tm.create_task = AsyncMock(side_effect=mock_create_task)

    with patch("src.services.planning_service.PlanningService._store_agent_config", new_callable=AsyncMock):
        svc = PlanningService(db, tm)
        await svc._create_tickets(session.id)

    repo = PlanRepository(db)
    updated_plan = await repo.get_by_session_id(session.id)
    assert updated_plan.status == "tickets_created"
    assert updated_plan.tm_epic_id == "tm-epic-1"
    total_tickets = 1 + 1 + 2  # 1 epic + 1 story + 2 tasks
    assert len(updated_plan.created_ticket_ids) == total_tickets

    session_repo = SessionRepository(db)
    updated_session = await session_repo.get_by_id(session.id)
    assert updated_session.status == "tickets_created"


# ---------------------------------------------------------------------------
# _create_tickets() — partial failure retry (idempotent)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tickets_partial_failure_retry_no_duplicates(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="Retry Project",
        tm_project_id="proj-retry",
        status="plan_confirmed",
    )
    db.add(session)
    await db.flush()
    plan = PromptPlan(
        session_id=session.id,
        status="confirmed",
        plan_content=VALID_PLAN_DICT,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    call_order = []
    task_call_count = 0

    async def mock_create_task_fail_second(project_id, task, story_tm_id, dep_tm_ids):
        nonlocal task_call_count
        task_call_count += 1
        call_order.append(task.local_id)
        if task_call_count == 2:
            raise UpstreamError("TM failure at task 2")
        return f"tm-{task.local_id}"

    tm = MagicMock()
    tm.create_epic = AsyncMock(return_value="tm-epic-1")
    tm.create_story = AsyncMock(return_value="tm-story-1")
    tm.create_task = AsyncMock(side_effect=mock_create_task_fail_second)

    with patch("src.services.planning_service.PlanningService._store_agent_config", new_callable=AsyncMock):
        svc = PlanningService(db, tm)
        await svc._create_tickets(session.id)

    repo = PlanRepository(db)
    partial_plan = await repo.get_by_session_id(session.id)
    assert partial_plan.status == "confirmed"
    first_task_id = partial_plan.ticket_id_map.get("task-1-1")
    assert first_task_id is not None

    task_call_count = 0
    call_order.clear()
    tm.create_task.side_effect = AsyncMock(
        side_effect=lambda project_id, task, story_tm_id, dep_tm_ids: f"tm-{task.local_id}"
    )

    with patch("src.services.planning_service.PlanningService._store_agent_config", new_callable=AsyncMock):
        svc2 = PlanningService(db, tm)
        await svc2._create_tickets(session.id)

    repo2 = PlanRepository(db)
    final_plan = await repo2.get_by_session_id(session.id)
    all_ids = list(final_plan.created_ticket_ids or [])
    assert len(all_ids) == len(set(all_ids)), "Duplicate ticket IDs found"


# ---------------------------------------------------------------------------
# _store_agent_config — failure does not block ticket creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_agent_config_failure_does_not_block(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="Config Fail Project",
        tm_project_id="proj-config-fail",
        status="plan_confirmed",
    )
    db.add(session)
    await db.flush()
    plan = PromptPlan(
        session_id=session.id,
        status="confirmed",
        plan_content=VALID_PLAN_DICT,
        agent_config={
            "project_id": "proj-config-fail",
            "tech_stack": ["Python"],
            "agent_overrides": [],
        },
    )
    db.add(plan)
    await db.commit()

    tm = _mock_tm_client()

    async def _store_fail(*args, **kwargs):
        raise Exception("ContextDistiller unreachable")

    with patch.object(PlanningService, "_store_agent_config", side_effect=_store_fail):
        svc = PlanningService(db, tm)
        await svc._create_tickets(session.id)

    repo = PlanRepository(db)
    final_plan = await repo.get_by_session_id(session.id)
    assert final_plan.status == "tickets_created"


# ---------------------------------------------------------------------------
# get_creation_status()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_creation_status_computes_total_correctly(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="Status Project",
        tm_project_id="proj-status",
        status="plan_confirmed",
    )
    db.add(session)
    await db.flush()
    plan = PromptPlan(
        session_id=session.id,
        status="confirmed",
        plan_content=VALID_PLAN_DICT,
        created_ticket_ids=["tm-epic-1"],
    )
    db.add(plan)
    await db.commit()

    tm = _mock_tm_client()
    svc = PlanningService(db, tm)
    status_resp = await svc.get_creation_status(session.id, svc_user.id)

    assert status_resp.total == 4  # 1 epic + 1 story + 2 tasks
    assert status_resp.created_count == 1


@pytest.mark.asyncio
async def test_get_creation_status_raises_not_found_for_missing_plan(db, svc_user):
    session = PromptSession(
        user_id=svc_user.id,
        session_type="new_project",
        tm_project_name="No Plan",
        status="approved",
    )
    db.add(session)
    await db.commit()

    tm = _mock_tm_client()
    svc = PlanningService(db, tm)
    with pytest.raises(NotFoundError):
        await svc.get_creation_status(session.id, svc_user.id)
