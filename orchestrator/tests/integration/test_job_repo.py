"""Integration tests — JobRepository against SQLite in-memory."""
import uuid
import pytest
from src.repositories.job_repo import JobRepository


@pytest.mark.asyncio
async def test_create_and_get_job(db):
    repo = JobRepository(db)
    job = await repo.create(
        job_type="orchestrate",
        ticket_id="t-1",
        project_id="p-1",
        triggered_by="user-x",
        payload={"foo": "bar"},
    )
    assert job.id is not None
    assert job.status == "pending"

    fetched = await repo.get_by_id(job.id)
    assert fetched.ticket_id == "t-1"
    assert fetched.payload == {"foo": "bar"}


@pytest.mark.asyncio
async def test_list_pending_returns_pending_only(db):
    repo = JobRepository(db)
    j1 = await repo.create(job_type="orchestrate", ticket_id="t-2", project_id="p-1",
                           triggered_by="u", payload={})
    j2 = await repo.create(job_type="orchestrate", ticket_id="t-3", project_id="p-1",
                           triggered_by="u", payload={})
    await repo.mark_running(j2.id)

    pending = await repo.list_pending()
    ids = [j.id for j in pending]
    assert j1.id in ids
    assert j2.id not in ids


@pytest.mark.asyncio
async def test_mark_done(db):
    repo = JobRepository(db)
    job = await repo.create(job_type="distill", ticket_id="t-4", project_id="p-1",
                            triggered_by="system", payload={})
    await repo.mark_running(job.id)
    await repo.mark_done(job.id, {"distilled": True})

    fetched = await repo.get_by_id(job.id)
    assert fetched.status == "done"
    assert fetched.result == {"distilled": True}
    assert fetched.finished_at is not None


@pytest.mark.asyncio
async def test_mark_failed(db):
    repo = JobRepository(db)
    job = await repo.create(job_type="orchestrate", ticket_id="t-5", project_id="p-1",
                            triggered_by="system", payload={})
    await repo.mark_failed(job.id, "something exploded")

    fetched = await repo.get_by_id(job.id)
    assert fetched.status == "failed"
    assert "exploded" in fetched.error_message


@pytest.mark.asyncio
async def test_has_running_job(db):
    repo = JobRepository(db)
    assert not await repo.has_running_job("t-99")
    job = await repo.create(job_type="orchestrate", ticket_id="t-99", project_id="p-1",
                            triggered_by="u", payload={})
    await repo.mark_running(job.id)
    assert await repo.has_running_job("t-99")


@pytest.mark.asyncio
async def test_priority_ordering(db):
    repo = JobRepository(db)
    low = await repo.create(job_type="orchestrate", ticket_id="t-lo", project_id="p-1",
                            priority=0, triggered_by="u", payload={})
    high = await repo.create(job_type="orchestrate", ticket_id="t-hi", project_id="p-1",
                             priority=5, triggered_by="u", payload={})
    pending = await repo.list_pending()
    ids = [j.id for j in pending]
    assert ids.index(high.id) < ids.index(low.id)


@pytest.mark.asyncio
async def test_list_all_with_filters(db):
    repo = JobRepository(db)
    await repo.create(job_type="orchestrate", ticket_id="filter-t", project_id="p-1",
                      triggered_by="u", payload={})
    jobs, total = await repo.list_all(ticket_id="filter-t")
    assert total >= 1
    assert all(j.ticket_id == "filter-t" for j in jobs)
