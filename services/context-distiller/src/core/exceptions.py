"""Domain exceptions."""


class UpstreamError(Exception):
    """External service (TM API, OpenAI) returned an error or was unreachable."""


class NotFoundError(Exception):
    """Requested resource does not exist."""


class ConflictError(Exception):
    """Operation violates an immutability or state-transition rule."""


class DistillationError(Exception):
    """LLM output failed YAML validation after all retries."""

    def __init__(self, message: str, raw_output: str = "") -> None:
        super().__init__(message)
        self.raw_output = raw_output
