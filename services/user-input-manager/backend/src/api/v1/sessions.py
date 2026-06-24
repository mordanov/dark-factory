import uuid

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_current_user, get_session_service
from src.core.auth_adapter import UserClaims
from src.schemas.schemas import (
    IterationResponse,
    RevertRequest,
    SessionCreate,
    SessionListResponse,
    SessionResponse,
    UserFeedback,
)
from src.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserClaims = Depends(get_current_user),
    svc: SessionService = Depends(get_session_service),
):
    return await svc.list_sessions(current_user.sub, offset=offset, limit=limit)


@router.post("", status_code=201)
async def create_session(
    payload: SessionCreate,
    current_user: UserClaims = Depends(get_current_user),
    svc: SessionService = Depends(get_session_service),
):
    return await svc.create_session(current_user.sub, payload)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID,
    current_user: UserClaims = Depends(get_current_user),
    svc: SessionService = Depends(get_session_service),
):
    return await svc.get_session(session_id, current_user.sub)


@router.get("/{session_id}/iterations", response_model=list[IterationResponse])
async def get_iterations(
    session_id: uuid.UUID,
    current_user: UserClaims = Depends(get_current_user),
    svc: SessionService = Depends(get_session_service),
):
    return await svc.get_iterations(session_id, current_user.sub)


@router.post("/{session_id}/feedback")
async def submit_feedback(
    session_id: uuid.UUID,
    payload: UserFeedback,
    current_user: UserClaims = Depends(get_current_user),
    svc: SessionService = Depends(get_session_service),
):
    return await svc.submit_feedback(session_id, current_user.sub, payload)


@router.post("/{session_id}/revert")
async def revert(
    session_id: uuid.UUID,
    payload: RevertRequest,
    current_user: UserClaims = Depends(get_current_user),
    svc: SessionService = Depends(get_session_service),
):
    return await svc.revert(session_id, current_user.sub, payload)
