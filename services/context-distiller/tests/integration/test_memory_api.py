"""Integration tests for memory and ADR API endpoints."""

from datetime import UTC, datetime, timezone

import pytest


async def test_get_memory_returns_200(test_client, mongo_db):
    await mongo_db.project_memory.insert_one(
        {
            "_id": "proj-1",
            "content": "project_id: proj-1\narchitecture: []",
            "version": 3,
            "last_ticket_id": "T-005",
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    resp = await test_client.get("/memory/proj-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == "proj-1"
    assert data["version"] == 3
    assert data["last_ticket_id"] == "T-005"
    assert "content" in data


async def test_get_memory_404_when_missing(test_client):
    resp = await test_client.get("/memory/nonexistent-proj")
    assert resp.status_code == 404


async def test_list_adrs_default_accepted(test_client, mongo_db):
    await mongo_db.adrs.insert_many(
        [
            {
                "_id": "ADR-001",
                "project_id": "proj-2",
                "title": "T1",
                "status": "accepted",
                "summary": "s",
                "content": "c",
                "ticket_id": "T-001",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            {
                "_id": "ADR-002",
                "project_id": "proj-2",
                "title": "T2",
                "status": "proposed",
                "summary": "s",
                "content": "c",
                "ticket_id": "T-002",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ]
    )
    resp = await test_client.get("/memory/proj-2/adrs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["adrs"]) == 1
    assert data["adrs"][0]["id"] == "ADR-001"


async def test_list_adrs_with_status_filter(test_client, mongo_db):
    await mongo_db.adrs.insert_many(
        [
            {
                "_id": "ADR-010",
                "project_id": "proj-3",
                "title": "T1",
                "status": "proposed",
                "summary": "s",
                "content": "c",
                "ticket_id": "T-001",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ]
    )
    resp = await test_client.get("/memory/proj-3/adrs?status=proposed")
    assert resp.status_code == 200
    assert len(resp.json()["adrs"]) == 1


async def test_list_adrs_all_status(test_client, mongo_db):
    await mongo_db.adrs.insert_many(
        [
            {
                "_id": "ADR-020",
                "project_id": "proj-4",
                "title": "T1",
                "status": "accepted",
                "summary": "s",
                "content": "c",
                "ticket_id": "T-001",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
            {
                "_id": "ADR-021",
                "project_id": "proj-4",
                "title": "T2",
                "status": "proposed",
                "summary": "s",
                "content": "c",
                "ticket_id": "T-002",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            },
        ]
    )
    resp = await test_client.get("/memory/proj-4/adrs?status=all")
    assert resp.status_code == 200
    assert len(resp.json()["adrs"]) == 2


async def test_create_adr_returns_201_and_id(test_client):
    resp = await test_client.post(
        "/memory/proj-5/adrs",
        json={
            "content": "# ADR-001\n## Status\nproposed",
            "ticket_id": "T-001",
            "title": "Use PostgreSQL",
            "summary": "PG for queue",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["adr_id"] == "ADR-001"


async def test_patch_adr_status_valid_transition(test_client, mongo_db):
    await mongo_db.adrs.insert_one(
        {
            "_id": "ADR-100",
            "project_id": "proj-6",
            "title": "T",
            "status": "proposed",
            "summary": "s",
            "content": "c",
            "ticket_id": "T-001",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    resp = await test_client.patch(
        "/memory/proj-6/adrs/ADR-100/status",
        json={"status": "accepted"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


async def test_patch_adr_status_invalid_transition_returns_409(test_client, mongo_db):
    await mongo_db.adrs.insert_one(
        {
            "_id": "ADR-101",
            "project_id": "proj-7",
            "title": "T",
            "status": "accepted",
            "summary": "s",
            "content": "c",
            "ticket_id": "T-001",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    resp = await test_client.patch(
        "/memory/proj-7/adrs/ADR-101/status",
        json={"status": "proposed"},
    )
    assert resp.status_code == 409


async def test_patch_adr_status_not_found_returns_404(test_client):
    resp = await test_client.patch(
        "/memory/proj-99/adrs/ADR-999/status",
        json={"status": "accepted"},
    )
    assert resp.status_code == 404
