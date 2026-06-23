"""Planning agent API — 5 endpoints for plan generation, editing, confirmation, and status."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.core.exceptions import AppError, BadRequestError, ConflictError
from src.db.session import get_db
from src.models.models import User
from src.schemas.schemas import (
    PlanConfirmResponse,
    PlanGenerateResponse,
    PlanResponse,
    PlanStatusResponse,
    PlanUpdateRequest,
)
from src.services.planning_service import PlanningService
from src.services.ticket_manager.client import get_ticket_manager_client
from src.services.ticket_manager.plan_client import TMPlanClient

router = APIRouter(prefix="/sessions", tags=["planning"])


def get_planning_service(
    db: AsyncSession = Depends(get_db),
    tm: TMPlanClient = Depends(lambda: TMPlanClient()),
) -> PlanningService:
    return PlanningService(db, tm)


@router.post("/{session_id}/plan", response_model=PlanGenerateResponse, status_code=202)
async def trigger_plan_generation(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: PlanningService = Depends(get_planning_service),
):
    try:
        return await svc.generate(session_id, current_user.id)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail)
    except AppError:
        raise


@router.get("/{session_id}/plan", response_model=PlanResponse)
async def get_plan(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: PlanningService = Depends(get_planning_service),
):
    return await svc.get_plan(session_id, current_user.id)


@router.put("/{session_id}/plan", response_model=PlanResponse)
async def update_plan(
    session_id: uuid.UUID,
    payload: PlanUpdateRequest,
    current_user: User = Depends(get_current_user),
    svc: PlanningService = Depends(get_planning_service),
):
    try:
        return await svc.update(session_id, current_user.id, payload.plan_content)
    except BadRequestError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": "Plan validation failed",
                "errors": exc.detail.split(": ", 1)[-1].split("; "),
            },
        )
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail)
    except AppError:
        raise


@router.post("/{session_id}/plan/confirm", response_model=PlanConfirmResponse, status_code=202)
async def confirm_plan(
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    svc: PlanningService = Depends(get_planning_service),
):
    try:
        return await svc.confirm(session_id, current_user.id, background_tasks)
    except ConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail)
    except AppError:
        raise


@router.get("/{session_id}/plan/status", response_model=PlanStatusResponse)
async def get_plan_status(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    svc: PlanningService = Depends(get_planning_service),
):
    return await svc.get_creation_status(session_id, current_user.id)
