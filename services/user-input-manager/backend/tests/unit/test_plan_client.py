"""Unit tests for TMPlanClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.schemas.schemas import PlanEpic, PlanStory, PlanTask
from src.services.ticket_manager.plan_client import TMPlanClient


def _client() -> TMPlanClient:
    c = TMPlanClient.__new__(TMPlanClient)
    c._request = AsyncMock()
    return c


def _epic() -> PlanEpic:
    return PlanEpic(
        local_id="epic-1",
        title="Build auth",
        description="JWT authentication system",
        ticket_type="epic",
    )


def _story() -> PlanStory:
    return PlanStory(
        local_id="story-1",
        title="Backend auth",
        description="JWT service",
        ticket_type="story",
        tasks=[],
    )


def _task() -> PlanTask:
    return PlanTask(
        local_id="task-1-1",
        title="Create JWT service",
        description="Token generation",
        ticket_type="task",
        complexity="M",
        depends_on=[],
    )


@pytest.mark.asyncio
async def test_create_epic_posts_correct_payload():
    client = _client()
    client._request.return_value = {"id": "tm-epic-abc"}

    result = await client.create_epic("proj-1", _epic())

    assert result == "tm-epic-abc"
    client._request.assert_awaited_once()
    call_kwargs = client._request.call_args
    assert call_kwargs[0][0] == "POST"
    payload = call_kwargs[1]["json"]
    assert payload["title"] == "Build auth"
    assert payload["type"] == "epic"
    assert payload["tags"] == []


@pytest.mark.asyncio
async def test_create_story_posts_correct_payload():
    client = _client()
    client._request.return_value = {"id": "tm-story-xyz"}

    result = await client.create_story("proj-1", _story(), "tm-epic-abc")

    assert result == "tm-story-xyz"
    payload = client._request.call_args[1]["json"]
    assert payload["title"] == "Backend auth"
    assert payload["type"] == "story"
    assert payload["tags"] == ["story"]
    assert payload["parent_id"] == "tm-epic-abc"


@pytest.mark.asyncio
async def test_create_task_posts_correct_payload():
    client = _client()
    client._request.return_value = {"id": "tm-task-001"}

    result = await client.create_task("proj-1", _task(), "tm-story-xyz", ["tm-dep-1"])

    assert result == "tm-task-001"
    payload = client._request.call_args[1]["json"]
    assert payload["title"] == "Create JWT service"
    assert payload["type"] == "task"
    assert payload["tags"] == ["complexity-M"]
    assert payload["parent_id"] == "tm-story-xyz"
    assert payload["depends_on"] == ["tm-dep-1"]


@pytest.mark.asyncio
async def test_create_task_complexity_tag_reflects_task_complexity():
    client = _client()
    client._request.return_value = {"id": "tm-task-xl"}
    task = _task()
    task = PlanTask(
        local_id="task-1-2",
        title="Large task",
        description="A large task",
        ticket_type="implementation",
        complexity="XL",
        depends_on=[],
    )

    await client.create_task("proj-1", task, "tm-story-1", [])

    payload = client._request.call_args[1]["json"]
    assert payload["tags"] == ["complexity-XL"]
    assert payload["type"] == "implementation"


@pytest.mark.asyncio
async def test_create_task_no_deps_passes_empty_list():
    client = _client()
    client._request.return_value = {"id": "tm-task-no-dep"}

    await client.create_task("proj-1", _task(), "tm-story-1", [])

    payload = client._request.call_args[1]["json"]
    assert payload["depends_on"] == []


@pytest.mark.asyncio
async def test_create_epic_returns_string_id():
    client = _client()
    client._request.return_value = {"id": 42}  # integer id from TM

    result = await client.create_epic("proj-1", _epic())

    assert result == "42"
    assert isinstance(result, str)
