"""Application exception hierarchy and FastAPI handlers.

Defining a clear hierarchy (SOLID / LSP) means every layer can raise
domain-specific errors that the HTTP layer translates cleanly without
leaking internals.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base for all application-level errors."""
    status_code: int = 500
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    detail = "Resource not found"


class UnauthorizedError(AppError):
    status_code = 401
    detail = "Not authenticated"


class ForbiddenError(AppError):
    status_code = 403
    detail = "Permission denied"


class ConflictError(AppError):
    status_code = 409
    detail = "Conflict"


class BadRequestError(AppError):
    status_code = 400
    detail = "Bad request"


class UpstreamError(AppError):
    """External service (OpenAI, Ticket Manager) returned an error."""
    status_code = 502
    detail = "Upstream service error"


# ---------------------------------------------------------------------------
# FastAPI handlers
# ---------------------------------------------------------------------------

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
