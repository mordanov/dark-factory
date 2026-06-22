"""Application exception hierarchy."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 500
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    detail = "Not found"


class BadRequestError(AppError):
    status_code = 400
    detail = "Bad request"


class UnauthorizedError(AppError):
    status_code = 401
    detail = "Not authenticated"


class ForbiddenError(AppError):
    status_code = 403
    detail = "Forbidden"


class ConflictError(AppError):
    status_code = 409
    detail = "Conflict"


class UpstreamError(AppError):
    status_code = 502
    detail = "Upstream error"


class FSMError(AppError):
    """Invalid FSM transition or state."""

    status_code = 422
    detail = "FSM error"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
