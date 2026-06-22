"""Unit tests for src.services.llm.openai_service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.core.exceptions import UpstreamError
from src.services.llm.openai_service import RefinementResult, _build_messages, refine_prompt


def test_build_messages_no_history():
    msgs = _build_messages("My prompt", [], None, None)
    assert len(msgs) == 1
    assert "My prompt" in msgs[0]["content"]
    assert "Project Context" not in msgs[0]["content"]


def test_build_messages_with_context():
    msgs = _build_messages("My prompt", [], "Existing tickets:\n- t1", None)
    content = msgs[0]["content"]
    assert "Project Context" in content
    assert "Existing tickets" in content


def test_build_messages_with_history():
    history = [
        {"role": "user", "iteration_number": 1, "text": "raw prompt", "questions": ""},
        {
            "role": "assistant",
            "iteration_number": 2,
            "text": "refined",
            "questions": "Can you clarify X?",
        },
    ]
    msgs = _build_messages("raw prompt", history, None, "Please add more detail")
    content = msgs[0]["content"]
    assert "Previous Refinement History" in content
    assert "Can you clarify X?" in content
    assert "Please add more detail" in content


@pytest.mark.asyncio
async def test_refine_prompt_success():
    fake_json = json.dumps(
        {
            "refined_prompt": "Refined version",
            "assessment": "Looks good",
            "questions": "",
            "suggested_title": "Short title",
            "is_ready": True,
        }
    )
    mock_choice = MagicMock()
    mock_choice.message.content = fake_json

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("src.services.llm.openai_service.AsyncOpenAI", return_value=mock_client):
        result = await refine_prompt("My prompt", [])

    assert isinstance(result, RefinementResult)
    assert result.refined_prompt == "Refined version"
    assert result.is_ready is True
    assert result.suggested_title == "Short title"


@pytest.mark.asyncio
async def test_refine_prompt_bad_json_raises():
    mock_choice = MagicMock()
    mock_choice.message.content = "not json at all"

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("src.services.llm.openai_service.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(UpstreamError, match="malformed"):
            await refine_prompt("prompt", [])


@pytest.mark.asyncio
async def test_refine_prompt_api_error_raises():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("network error"))

    with patch("src.services.llm.openai_service.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(UpstreamError, match="LLM service unavailable"):
            await refine_prompt("prompt", [])
