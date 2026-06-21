import time
from datetime import datetime, timezone
from typing import Any

from src.schemas import ToolEnvelope, ToolError


def build_success(tool_name: str, result: dict[str, Any], start_time: float) -> ToolEnvelope:
    return ToolEnvelope(
        tool=tool_name,
        success=True,
        result=result,
        error=None,
        duration_ms=int((time.monotonic() - start_time) * 1000),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def build_error(
    tool_name: str,
    code: str,
    message: str,
    retryable: bool,
    start_time: float,
) -> ToolEnvelope:
    return ToolEnvelope(
        tool=tool_name,
        success=False,
        result=None,
        error=ToolError(code=code, message=message, retryable=retryable),
        duration_ms=int((time.monotonic() - start_time) * 1000),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
