from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.user import User
from src.schemas.admin import AdminUserCreate, AdminUserUpdate

_log = structlog.get_logger(__name__)


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.email))
    return list(result.scalars().all())


async def create_user(session: AsyncSession, actor: User, data: AdminUserCreate) -> User:
    existing = await session.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists",
        )

    new_user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    session.add(new_user)
    await session.flush()

    _log.info(
        "admin_user_created",
        event_type="admin_user_created",
        actor_id=str(actor.id),
        target_user_id=str(new_user.id),
        target_email=data.email,
        target_role=data.role.value,
    )
    await session.commit()
    await session.refresh(new_user)
    return new_user


async def update_user(
    session: AsyncSession, actor: User, user_id: UUID, data: AdminUserUpdate
) -> User:
    user = await _get_user_or_404(session, user_id)

    if actor.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators cannot edit their own account via this endpoint",
        )

    changes: dict[str, object] = {}
    if data.email is not None and data.email != user.email:
        existing = await session.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A user with this email already exists",
            )
        user.email = data.email
        changes["email"] = data.email
    if data.role is not None and data.role != user.role:
        user.role = data.role
        changes["role"] = data.role.value
    if data.password is not None:
        user.hashed_password = hash_password(data.password)
        _log.info(
            "admin_user_password_reset",
            event_type="admin_user_password_reset",
            actor_id=str(actor.id),
            target_user_id=str(user.id),
            target_email=user.email,
        )

    _log.info(
        "admin_user_updated",
        event_type="admin_user_updated",
        actor_id=str(actor.id),
        target_user_id=str(user.id),
        changes=changes,
    )
    await session.commit()
    await session.refresh(user)
    return user


async def block_user(session: AsyncSession, actor: User, user_id: UUID) -> User:
    user = await _get_user_or_404(session, user_id)

    if actor.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators cannot block their own account",
        )

    if user.is_blocked:
        return user  # idempotent — already blocked, no state change needed

    user.blocked_at = datetime.now(UTC)
    _log.info(
        "admin_user_blocked",
        event_type="admin_user_blocked",
        actor_id=str(actor.id),
        target_user_id=str(user.id),
        blocked_at=user.blocked_at.isoformat(),
    )
    await session.commit()
    await session.refresh(user)
    return user


async def unblock_user(session: AsyncSession, actor: User, user_id: UUID) -> User:
    user = await _get_user_or_404(session, user_id)

    if not user.is_blocked:
        return user  # idempotent — already active, no state change needed

    user.blocked_at = None
    _log.info(
        "admin_user_unblocked",
        event_type="admin_user_unblocked",
        actor_id=str(actor.id),
        target_user_id=str(user.id),
    )
    await session.commit()
    await session.refresh(user)
    return user


async def _get_user_or_404(session: AsyncSession, user_id: UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user
