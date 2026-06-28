"""Peer consultation API — POST /api/v1/consult."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth_adapter import KeycloakValidator, UnauthorizedError, UserClaims
from src.db.session import get_db
from src.schemas.schemas import ConsultRequest, ConsultResponse
from src.services.consultation_service import (
    ConsultationService,
    ConsultationTimeoutError,
    PeerNotAvailableError,
)

logger = structlog.get_logger(__name__)
router = APIRouter()
security = HTTPBearer()
_adapter = KeycloakValidator()


async def _verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserClaims:
    try:
        return await _adapter.verify(credentials.credentials)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/consult", response_model=ConsultResponse)
async def consult(
    body: ConsultRequest,
    db: AsyncSession = Depends(get_db),
    _: UserClaims = Depends(_verify_token),
) -> ConsultResponse:
    svc = ConsultationService(db)
    try:
        result = await svc.consult(body)
        await db.commit()
    except PeerNotAvailableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConsultationTimeoutError as exc:
        raise HTTPException(status_code=408, detail=str(exc)) from exc
    return result
