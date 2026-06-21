"""Integration tests — /api/v1/auth endpoints."""
import pytest


@pytest.mark.asyncio
async def test_login_success(client, regular_user):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "user@test.com",
        "password": "User1234!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client, regular_user):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "user@test.com",
        "password": "WrongPassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client):
    resp = await client.post("/api/v1/auth/login", json={
        "email": "nobody@test.com",
        "password": "whatever",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client, regular_user):
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "user@test.com",
        "password": "User1234!",
    })
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_refresh_with_access_token_fails(client, user_token):
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": user_token})
    assert resp.status_code == 401
