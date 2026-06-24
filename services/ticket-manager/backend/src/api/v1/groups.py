from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.security import get_current_user
from src.models.user import User
from src.schemas.project_group import (
    ProjectGroupCreate,
    ProjectGroupListResponse,
    ProjectGroupResponse,
    ProjectGroupUpdate,
)
from src.services import project_group_service

router = APIRouter(tags=["Groups"])


@router.post("/groups", response_model=ProjectGroupResponse, status_code=201)
async def create_group(
    body: ProjectGroupCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProjectGroupResponse:
    return await project_group_service.create_group(db, body)


@router.get("/groups", response_model=ProjectGroupListResponse, status_code=200)
async def list_groups(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProjectGroupListResponse:
    return await project_group_service.list_groups(db)


@router.get("/groups/{group_id}", response_model=ProjectGroupResponse, status_code=200)
async def get_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProjectGroupResponse:
    return await project_group_service.get_group(db, group_id)


@router.patch("/groups/{group_id}", response_model=ProjectGroupResponse, status_code=200)
async def update_group(
    group_id: UUID,
    body: ProjectGroupUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ProjectGroupResponse:
    return await project_group_service.update_group(db, group_id, body)


@router.delete("/groups/{group_id}", status_code=204)
async def delete_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> None:
    await project_group_service.delete_group(db, group_id)
