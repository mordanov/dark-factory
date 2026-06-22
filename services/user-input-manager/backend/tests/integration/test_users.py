"""Integration tests — /api/v1/users (admin) endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_users_as_admin(client, admin_headers, admin_user):
    resp = await client.get("/api/v1/users", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_users_forbidden_for_regular(client, auth_headers):
    resp = await client.get("/api/v1/users", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user(client, admin_headers):
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "newuser@test.com",
            "password": "NewPass1234!",
            "full_name": "New User",
            "is_admin": False,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@test.com"
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_create_duplicate_user(client, admin_headers, regular_user):
    resp = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "user@test.com",
            "password": "SomePass123!",
            "full_name": "Duplicate",
            "is_admin": False,
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_user_block(client, admin_headers, regular_user):
    resp = await client.patch(
        f"/api/v1/users/{regular_user.id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_get_user_not_found(client, admin_headers):
    import uuid

    resp = await client.get(f"/api/v1/users/{uuid.uuid4()}", headers=admin_headers)
    assert resp.status_code == 404
