from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.project import Project
from src.models.project_group import ProjectGroup
from src.schemas.project_group import ProjectGroupCreate, ProjectGroupUpdate
from src.services import project_group_service


async def _default_group(session: AsyncSession) -> ProjectGroup:
    result = await session.execute(select(ProjectGroup).where(ProjectGroup.identifier == "DEFAULT"))
    return result.scalar_one()


@pytest.mark.asyncio
async def test_identifier_normalized_to_uppercase(db_session: AsyncSession):
    resp = await project_group_service.create_group(
        db_session, ProjectGroupCreate(identifier="lower", name="Lower Test")
    )
    assert resp.identifier == "LOWER"


@pytest.mark.asyncio
async def test_project_count_on_list(db_session: AsyncSession):
    from src.core.security import hash_password
    from src.models.user import User, UserRole

    user = User(email=f"{uuid4()}@t.com", hashed_password=hash_password("pw"), role=UserRole.user)
    db_session.add(user)
    await db_session.flush()

    group = ProjectGroup(identifier="CNTG1", name="Count Group")
    db_session.add(group)
    await db_session.flush()

    project = Project(name="P1", slug=f"p-{uuid4()}", group_id=group.id, created_by=user.id)
    db_session.add(project)
    await db_session.commit()

    result = await project_group_service.list_groups(db_session)
    group_resp = next(g for g in result.items if g.identifier == "CNTG1")
    assert group_resp.project_count == 1


@pytest.mark.asyncio
async def test_auto_assign_default_group_via_get_default(db_session: AsyncSession):
    default_id = await project_group_service.get_default_group_id(db_session)
    default = await _default_group(db_session)
    assert default_id == default.id


@pytest.mark.asyncio
async def test_delete_system_group_raises(db_session: AsyncSession):
    from fastapi import HTTPException

    default = await _default_group(db_session)
    with pytest.raises(HTTPException) as exc_info:
        await project_group_service.delete_group(db_session, default.id)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_update_group_name_and_description(db_session: AsyncSession):
    group = ProjectGroup(identifier="UPDI1", name="Old Name")
    db_session.add(group)
    await db_session.commit()

    resp = await project_group_service.update_group(
        db_session,
        group.id,
        ProjectGroupUpdate(name="New Name", description="A description"),
    )
    assert resp.name == "New Name"
    assert resp.description == "A description"
