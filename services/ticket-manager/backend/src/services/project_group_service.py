from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.project import Project
from src.models.project_group import ProjectGroup
from src.schemas.project_group import (
    ProjectGroupCreate,
    ProjectGroupListResponse,
    ProjectGroupResponse,
    ProjectGroupUpdate,
)

_log = structlog.get_logger(__name__)


def _to_response(group: ProjectGroup, project_count: int = 0) -> ProjectGroupResponse:
    return ProjectGroupResponse(
        id=group.id,
        identifier=group.identifier,
        name=group.name,
        description=group.description,
        is_system=group.is_system,
        created_at=group.created_at,
        project_count=project_count,
    )


async def _get_or_404(session: AsyncSession, group_id: UUID) -> ProjectGroup:
    group = await session.get(ProjectGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project group not found")
    return group


async def _count_projects(session: AsyncSession, group_id: UUID) -> int:
    result = await session.execute(select(func.count()).where(Project.group_id == group_id))
    return result.scalar_one()


async def create_group(
    session: AsyncSession,
    data: ProjectGroupCreate,
) -> ProjectGroupResponse:
    group = ProjectGroup(
        identifier=data.identifier,
        name=data.name,
        description=data.description,
    )
    session.add(group)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Group identifier '{data.identifier}' already exists",
        )
    await session.commit()
    await session.refresh(group)
    _log.info("project_group_created", identifier=group.identifier, group_id=str(group.id))
    return _to_response(group, 0)


async def list_groups(session: AsyncSession) -> ProjectGroupListResponse:
    groups_result = await session.execute(select(ProjectGroup).order_by(ProjectGroup.created_at))
    groups = groups_result.scalars().all()

    items = []
    for group in groups:
        count = await _count_projects(session, group.id)
        items.append(_to_response(group, count))

    return ProjectGroupListResponse(items=items, total=len(items))


async def get_group(session: AsyncSession, group_id: UUID) -> ProjectGroupResponse:
    group = await _get_or_404(session, group_id)
    count = await _count_projects(session, group_id)
    return _to_response(group, count)


async def update_group(
    session: AsyncSession,
    group_id: UUID,
    data: ProjectGroupUpdate,
) -> ProjectGroupResponse:
    group = await _get_or_404(session, group_id)

    if data.name is not None:
        group.name = data.name
    if data.description is not None:
        group.description = data.description

    await session.commit()
    await session.refresh(group)
    count = await _count_projects(session, group_id)
    _log.info("project_group_updated", group_id=str(group_id))
    return _to_response(group, count)


async def delete_group(session: AsyncSession, group_id: UUID) -> None:
    group = await _get_or_404(session, group_id)

    if group.is_system:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Default group is a system group and cannot be deleted",
        )

    count = await _count_projects(session, group_id)
    if count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Group still has {count} project(s) linked to it; reassign or delete them first",
        )

    await session.delete(group)
    await session.commit()
    _log.info("project_group_deleted", group_id=str(group_id))


async def get_default_group_id(session: AsyncSession) -> UUID:
    result = await session.execute(select(ProjectGroup).where(ProjectGroup.identifier == "DEFAULT"))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Default project group not found — run database migrations",
        )
    return group.id
