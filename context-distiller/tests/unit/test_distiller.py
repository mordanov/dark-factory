"""Unit tests for distiller.py — YAML validation and retry logic."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.exceptions import DistillationError, UpstreamError
from src.services.data_collector import CollectedContext
from src.services.distiller import _validate_yaml, distill


VALID_YAML = """\
project_id: proj-1
last_updated: "2026-06-20T10:00:00Z"
last_ticket_id: T-001
architecture:
  - "JWT middleware added"
recent_changes:
  - ticket_id: T-001
    summary: "Added auth"
    files_changed: []
    risks: []
open_risks: []
known_constraints:
  - "All async"
tech_stack:
  backend: "Python"
  frontend: "N/A"
  database: "PG"
  infra: "Docker"
"""


def test_validate_yaml_passes_valid():
    result = _validate_yaml(VALID_YAML)
    assert result == VALID_YAML


def test_validate_yaml_raises_on_invalid_yaml():
    with pytest.raises(ValueError, match="YAML parse error"):
        _validate_yaml("not: valid: yaml: :::")


def test_validate_yaml_raises_on_missing_keys():
    incomplete = "project_id: p\nlast_updated: t\n"
    with pytest.raises(ValueError, match="Missing required keys"):
        _validate_yaml(incomplete)


def test_validate_yaml_raises_on_non_mapping():
    with pytest.raises(ValueError, match="not a YAML mapping"):
        _validate_yaml("- item1\n- item2\n")


@pytest.fixture
def sample_context():
    return CollectedContext(
        ticket_id="T-001",
        project_id="proj-1",
        ticket={"id": "T-001", "title": "Test"},
        audit_trail=[],
        current_memory=None,
        adr_refs=[],
    )


async def test_distill_returns_valid_yaml_on_first_attempt(sample_context):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = VALID_YAML

    with patch("src.services.distiller.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai.return_value = mock_client

        result = await distill(sample_context)

    assert "project_id" in result


async def test_distill_retries_on_parse_failure(sample_context):
    bad_response = MagicMock()
    bad_response.choices = [MagicMock()]
    bad_response.choices[0].message.content = "not valid yaml :::"

    good_response = MagicMock()
    good_response.choices = [MagicMock()]
    good_response.choices[0].message.content = VALID_YAML

    with patch("src.services.distiller.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[bad_response, bad_response, good_response]
        )
        mock_openai.return_value = mock_client

        result = await distill(sample_context)

    assert "project_id" in result
    assert mock_client.chat.completions.create.call_count == 3


async def test_distill_raises_after_three_failures(sample_context):
    bad_response = MagicMock()
    bad_response.choices = [MagicMock()]
    bad_response.choices[0].message.content = "invalid :::"

    with patch("src.services.distiller.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=bad_response)
        mock_openai.return_value = mock_client

        with pytest.raises(DistillationError):
            await distill(sample_context)

    assert mock_client.chat.completions.create.call_count == 3


async def test_distill_raises_upstream_on_llm_error(sample_context):
    with patch("src.services.distiller.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("connection refused")
        )
        mock_openai.return_value = mock_client

        with pytest.raises(UpstreamError):
            await distill(sample_context)
