"""
Integration test for the blocked-user login flow (T024).

Flow: create user → block via admin → attempt login → expect 403
      → unblock via admin → attempt login → expect 200
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password
from src.models.user import User, UserRole


async def _create_admin(session: AsyncSession, email: str) -> User:
    admin = User(
        email=email,
        hashed_password=hash_password("adminpass1"),
        role=UserRole.administrator,
    )
    session.add(admin)
    await session.flush()
    return admin


async def _create_regular_user(session: AsyncSession, email: str, password: str) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=UserRole.user,
    )
    session.add(user)
    await session.flush()
    return user


def _admin_token_headers(admin: User) -> dict:
    from src.core.security import create_access_token

    token = create_access_token(str(admin.id), admin.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_blocked_user_cannot_login_then_unblock_restores_access(
    client: AsyncClient, db_session: AsyncSession
):
    """
    Full lifecycle: create user → confirm login works → block via admin API
    → login rejected with 403 → unblock via admin API → login succeeds again.
    """
    password = "userpass99"
    user_email = f"target-{uuid4()}@test.com"
    admin_email = f"admin-{uuid4()}@test.com"

    admin = await _create_admin(db_session, admin_email)
    user = await _create_regular_user(db_session, user_email, password)
    await db_session.commit()

    # Step 1: confirm the user can log in before blocking
    pre_block_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": password},
    )
    assert pre_block_resp.status_code == 200, "user should be able to login before being blocked"

    # Step 2: admin blocks the user
    block_resp = await client.post(
        f"/api/v1/admin/users/{user.id}/block",
        headers=_admin_token_headers(admin),
    )
    assert block_resp.status_code == 200
    assert block_resp.json()["blocked_at"] is not None

    # Step 3: blocked user login attempt must be rejected with 403
    blocked_login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": password},
    )
    assert blocked_login_resp.status_code == 403
    detail = blocked_login_resp.json().get("detail", "")
    assert "blocked" in detail.lower(), f"expected 'blocked' in error detail, got: {detail!r}"

    # Step 4: admin unblocks the user
    unblock_resp = await client.post(
        f"/api/v1/admin/users/{user.id}/unblock",
        headers=_admin_token_headers(admin),
    )
    assert unblock_resp.status_code == 200
    assert unblock_resp.json()["blocked_at"] is None

    # Step 5: unblocked user can log in again
    post_unblock_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": password},
    )
    assert post_unblock_resp.status_code == 200, (
        "user should be able to login after being unblocked"
    )
    assert "access_token" in post_unblock_resp.json()


@pytest.mark.asyncio
async def test_blocked_user_wrong_password_still_401(client: AsyncClient, db_session: AsyncSession):
    """
    A blocked user with wrong password gets 401 (credential check before block check
    is an implementation choice; this test verifies the response is at least non-200).
    Both 401 and 403 are acceptable — we assert the login fails.
    """
    password = "correctpassword1"
    user_email = f"blocked-{uuid4()}@test.com"
    admin_email = f"admin-{uuid4()}@test.com"

    admin = await _create_admin(db_session, admin_email)
    user = await _create_regular_user(db_session, user_email, password)
    await db_session.commit()

    await client.post(
        f"/api/v1/admin/users/{user.id}/block",
        headers=_admin_token_headers(admin),
    )

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": "wrongpassword"},
    )
    assert resp.status_code in (401, 403), f"expected 401 or 403, got {resp.status_code}"


@pytest.mark.asyncio
async def test_active_user_login_unaffected_by_other_blocks(
    client: AsyncClient, db_session: AsyncSession
):
    """Blocking one user does not affect other active users."""
    password = "userpass99"
    admin_email = f"admin-{uuid4()}@test.com"
    blocked_email = f"blocked-{uuid4()}@test.com"
    active_email = f"active-{uuid4()}@test.com"

    admin = await _create_admin(db_session, admin_email)
    blocked_user = await _create_regular_user(db_session, blocked_email, password)
    await _create_regular_user(db_session, active_email, password)
    await db_session.commit()

    await client.post(
        f"/api/v1/admin/users/{blocked_user.id}/block",
        headers=_admin_token_headers(admin),
    )

    # Active user should still log in normally
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": active_email, "password": password},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()
