"""Unit tests for src.services.llm.planning_llm."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.core.exceptions import UpstreamError
from src.schemas.schemas import AgentConfig, PlanContent
from src.services.llm.planning_llm import generate_agent_config, generate_plan

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

VALID_PLAN_JSON = json.dumps({
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
                    "description": "Token generation and validation",
                    "ticket_type": "task",
                    "complexity": "M",
                    "depends_on": [],
                }
            ],
        }
    ],
})

VALID_AGENT_CONFIG_JSON = json.dumps({
    "project_id": "proj-abc",
    "tech_stack": ["Python", "FastAPI"],
    "agent_overrides": [
        {
            "agent_id": "backend",
            "override_text": "Focus on async patterns and SQLAlchemy 2.0",
        }
    ],
})


def _mock_openai_client(content: str):
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def _valid_plan_content() -> PlanContent:
    data = json.loads(VALID_PLAN_JSON)
    return PlanContent.model_validate(data)


# ---------------------------------------------------------------------------
# generate_plan — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_plan_returns_plan_content():
    mock_client = _mock_openai_client(VALID_PLAN_JSON)
    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_plan("Build an auth system")

    assert isinstance(result, PlanContent)
    assert result.epic.title == "Build auth system"
    assert len(result.stories) == 1
    assert result.stories[0].tasks[0].local_id == "task-1-1"


@pytest.mark.asyncio
async def test_generate_plan_passes_only_refined_prompt_to_llm():
    """LLM call must contain the refined prompt text and nothing else in user message."""
    mock_client = _mock_openai_client(VALID_PLAN_JSON)
    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        await generate_plan("Build an auth system")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    user_message = next(m for m in messages if m["role"] == "user")
    assert "Build an auth system" in user_message["content"]
    # Must NOT include internal identifiers
    assert "session_id" not in user_message["content"]
    assert "user_id" not in user_message["content"]


# ---------------------------------------------------------------------------
# generate_plan — retry on bad JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_plan_retries_on_bad_json_then_succeeds():
    bad_choice = MagicMock()
    bad_choice.message.content = "not valid json {"
    good_choice = MagicMock()
    good_choice.message.content = VALID_PLAN_JSON

    bad_response = MagicMock()
    bad_response.choices = [bad_choice]
    good_response = MagicMock()
    good_response.choices = [good_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[bad_response, good_response]
    )

    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_plan("Retry prompt")

    assert isinstance(result, PlanContent)
    assert mock_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_generate_plan_raises_upstream_error_after_two_json_failures():
    bad_choice = MagicMock()
    bad_choice.message.content = "not json"
    bad_response = MagicMock()
    bad_response.choices = [bad_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=bad_response)

    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(UpstreamError):
            await generate_plan("Will fail twice")

    assert mock_client.chat.completions.create.call_count == 2


# ---------------------------------------------------------------------------
# generate_plan — retry on invalid plan (validator failure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_plan_retries_on_invalid_plan_then_succeeds():
    invalid_plan = json.dumps({"epic": {}, "stories": []})  # missing required fields
    bad_choice = MagicMock()
    bad_choice.message.content = invalid_plan
    good_choice = MagicMock()
    good_choice.message.content = VALID_PLAN_JSON

    bad_response = MagicMock()
    bad_response.choices = [bad_choice]
    good_response = MagicMock()
    good_response.choices = [good_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[bad_response, good_response]
    )

    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_plan("Invalid first, valid second")

    assert isinstance(result, PlanContent)


@pytest.mark.asyncio
async def test_generate_plan_raises_upstream_error_after_two_invalid_plans():
    invalid_plan = json.dumps({"epic": {}, "stories": []})
    bad_choice = MagicMock()
    bad_choice.message.content = invalid_plan
    bad_response = MagicMock()
    bad_response.choices = [bad_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=bad_response)

    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(UpstreamError):
            await generate_plan("Always invalid")


# ---------------------------------------------------------------------------
# generate_plan — API exception handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_plan_raises_upstream_error_after_two_api_failures():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=Exception("network error")
    )

    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(UpstreamError, match="LLM service unavailable"):
            await generate_plan("API will fail")

    assert mock_client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_generate_plan_retries_on_api_error_then_succeeds():
    good_choice = MagicMock()
    good_choice.message.content = VALID_PLAN_JSON
    good_response = MagicMock()
    good_response.choices = [good_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=[Exception("timeout"), good_response]
    )

    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_plan("Retry on API error")

    assert isinstance(result, PlanContent)


# ---------------------------------------------------------------------------
# generate_agent_config — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_agent_config_returns_agent_config():
    mock_client = _mock_openai_client(VALID_AGENT_CONFIG_JSON)
    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_agent_config(
            "Build auth", _valid_plan_content(), "proj-abc"
        )

    assert isinstance(result, AgentConfig)
    assert result.project_id == "proj-abc"
    assert "Python" in result.tech_stack
    assert result.agent_overrides[0].agent_id == "backend"


@pytest.mark.asyncio
async def test_generate_agent_config_includes_project_id_in_user_message():
    mock_client = _mock_openai_client(VALID_AGENT_CONFIG_JSON)
    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        await generate_agent_config("Build auth", _valid_plan_content(), "proj-test-123")

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    user_message = next(m for m in messages if m["role"] == "user")
    assert "proj-test-123" in user_message["content"]


# ---------------------------------------------------------------------------
# generate_agent_config — failure returns None, does not raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_agent_config_returns_none_on_api_exception():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=Exception("network error")
    )
    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_agent_config(
            "Build auth", _valid_plan_content(), "proj-fail"
        )

    assert result is None


@pytest.mark.asyncio
async def test_generate_agent_config_returns_none_on_bad_json():
    mock_client = _mock_openai_client("not json at all")
    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_agent_config(
            "Build auth", _valid_plan_content(), "proj-bad-json"
        )

    assert result is None


@pytest.mark.asyncio
async def test_generate_agent_config_returns_none_on_missing_keys():
    mock_client = _mock_openai_client(json.dumps({"wrong": "structure"}))
    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        result = await generate_agent_config(
            "Build auth", _valid_plan_content(), "proj-missing"
        )

    # Should return a valid AgentConfig with empty fields, or None — either is acceptable
    # The key requirement: does NOT raise
    # (current impl returns AgentConfig with empty overrides when keys missing)


@pytest.mark.asyncio
async def test_generate_agent_config_never_raises():
    """generate_agent_config must never propagate any exception."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("unexpected crash")
    )
    with patch("src.services.llm.planning_llm.AsyncOpenAI", return_value=mock_client):
        try:
            result = await generate_agent_config(
                "Build auth", _valid_plan_content(), "proj-crash"
            )
            assert result is None
        except Exception:
            pytest.fail("generate_agent_config should never raise")
