import asyncio
import logging

from sqlalchemy import select

import src.models  # noqa: F401 — registers all mappers before any query runs
from src.core.config import settings
from src.core.database import AsyncSessionLocal
from src.core.security import hash_password
from src.models.user import User, UserRole

logger = logging.getLogger(__name__)


async def _ensure_user(email: str, password: str, role: UserRole) -> None:
    if not email or not password:
        return
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none() is not None:
            return
        session.add(User(email=email, hashed_password=hash_password(password), role=role))
        await session.commit()
        logger.info("Created default %s: %s", role.value, email)


async def seed_default_users() -> None:
    await _ensure_user(
        settings.default_admin_email,
        settings.default_admin_password,
        UserRole.administrator,
    )
    await _ensure_user(
        settings.default_user_email,
        settings.default_user_password,
        UserRole.user,
    )


if __name__ == "__main__":
    asyncio.run(seed_default_users())
