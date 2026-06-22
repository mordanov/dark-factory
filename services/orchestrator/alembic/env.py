"""Alembic async migrations env."""

import asyncio
from logging.config import fileConfig

import src.models.models  # noqa
from sqlalchemy.ext.asyncio import create_async_engine
from src.core.config import get_settings
from src.db.postgres import Base

from alembic import context

config = context.config
settings = get_settings()
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=settings.database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: context.configure(connection=c, target_metadata=target_metadata)
        )
        async with engine.begin() as conn2:
            await conn2.run_sync(lambda c: context.run_migrations())
    await engine.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
