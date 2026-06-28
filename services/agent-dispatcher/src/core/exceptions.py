"""Application exception hierarchy."""

from __future__ import annotations


class AppError(Exception):
    """Base application error. Maps to HTTP 400/500."""

    status_code: int = 500

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class PromptNotFoundError(AppError):
    status_code = 404

    def __init__(self, agent_id: str) -> None:
        super().__init__(f"No prompt file found for agent '{agent_id}'")


class AgentRunConflictError(AppError):
    status_code = 409

    def __init__(self, ticket_id: str) -> None:
        super().__init__(f"Agent run already active for ticket '{ticket_id}'")


class OrchestratorError(AppError):
    status_code = 502

    def __init__(self, detail: str = "Orchestrator request failed") -> None:
        super().__init__(detail)


class TMCommentError(AppError):
    status_code = 502

    def __init__(self, detail: str = "Ticket Manager comment failed") -> None:
        super().__init__(detail)


class UpstreamError(AppError):
    """Raised when an upstream CLI tool or external service call fails."""

    status_code = 502

    def __init__(self, detail: str = "Upstream service error") -> None:
        super().__init__(detail)
