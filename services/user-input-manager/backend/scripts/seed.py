#!/usr/bin/env python3
"""Seed script — creates the initial admin user if it doesn't exist.

Run once after `alembic upgrade head`:
    python scripts/seed.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from src.core.config import get_settings
from src.core.security import hash_password
from src.db.session import AsyncSessionFactory, Base, engine
from src.models.models import User  # noqa


async def seed() -> None:
    settings = get_settings()

    async with AsyncSessionFactory() as session:
        existing = await session.execute(
            select(User).where(User.email == settings.initial_admin_email.lower())
        )
        if existing.scalar_one_or_none():
            print(f"Admin user '{settings.initial_admin_email}' already exists — skipping.")
            return

        admin = User(
            email=settings.initial_admin_email.lower(),
            password_hash=hash_password(settings.initial_admin_password),
            full_name="Administrator",
            is_admin=True,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print(f"✓ Admin user created: {settings.initial_admin_email}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
