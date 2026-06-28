"""Integration-test fixtures for agent-dispatcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_capability_registry():
    """Auto-mock get_registry() so integration tests don't require a loaded registry."""
    registry = MagicMock()
    registry.get_brainstorm_participants.return_value = []
    registry.to_yaml_string.return_value = "version: '1.0'\nagents: []"
    registry.brainstorm_project_name.side_effect = lambda ticket_id: f"df-{ticket_id}"

    with patch("src.services.capability_registry.get_registry", return_value=registry):
        yield registry
