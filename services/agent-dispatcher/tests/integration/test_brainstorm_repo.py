"""Integration tests for BrainstormSessionRepository."""

from __future__ import annotations

import pytest
from src.repositories.brainstorm_repo import BrainstormSessionRepository


@pytest.fixture
async def repo(db_session):
    return BrainstormSessionRepository(db_session)


async def test_get_or_create_creates_on_first_call(repo):
    session = await repo.get_or_create("TKT-BS-001", max_rounds=3)
    assert session.id is not None
    assert session.ticket_id == "TKT-BS-001"
    assert session.project_name == "df-TKT-BS-001"
    assert session.status == "active"
    assert session.current_round == 1
    assert session.max_rounds == 3


async def test_get_or_create_returns_existing_on_second_call(repo):
    s1 = await repo.get_or_create("TKT-BS-002")
    s2 = await repo.get_or_create("TKT-BS-002")
    assert s1.id == s2.id


async def test_increment_round(repo):
    session = await repo.get_or_create("TKT-BS-003", max_rounds=5)
    assert session.current_round == 1

    await repo.increment_round(session.id)

    from sqlalchemy import select
    from src.models.models import BrainstormSession

    result = await repo.db.execute(
        select(BrainstormSession).where(BrainstormSession.id == session.id)
    )
    updated = result.scalar_one()
    assert updated.current_round == 2


async def test_conclude_sets_status_and_consensus(repo):
    session = await repo.get_or_create("TKT-BS-004")
    await repo.conclude(session.id, "agreed")

    from sqlalchemy import select
    from src.models.models import BrainstormSession

    result = await repo.db.execute(
        select(BrainstormSession).where(BrainstormSession.id == session.id)
    )
    updated = result.scalar_one()
    assert updated.status == "concluded"
    assert updated.consensus == "agreed"
    assert updated.concluded_at is not None
