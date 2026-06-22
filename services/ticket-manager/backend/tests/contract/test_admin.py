from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.models.user import User, UserRole


async def _create_user(
    session: AsyncSession,
    email: str,
    role: UserRole = UserRole.user,
) -> User:
    user = User(email=email, hashed_password=hash_password("password123"), role=role)
    session.add(user)
    await session.flush()
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token(str(user.id), user.role.value)
    return {"Authorization": f"Bearer {token}"}


# ── GET /admin/users ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_list_users_200(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target = await _create_user(db_session, f"user-{uuid4()}@test.com")
    await db_session.commit()

    resp = await client.get("/api/v1/admin/users", headers=_auth_headers(admin))
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    ids = [item["id"] for item in data["items"]]
    assert str(target.id) in ids
    assert str(admin.id) in ids


@pytest.mark.asyncio
async def test_admin_list_users_403_non_admin(client: AsyncClient, db_session: AsyncSession):
    regular = await _create_user(db_session, f"user-{uuid4()}@test.com")
    await db_session.commit()

    resp = await client.get("/api/v1/admin/users", headers=_auth_headers(regular))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_users_401_unauthenticated(client: AsyncClient, db_session: AsyncSession):
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 401


# ── POST /admin/users ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_create_user_201(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    await db_session.commit()

    new_email = f"new-{uuid4()}@test.com"
    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": new_email, "password": "securepass1", "role": "user"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == new_email
    assert data["role"] == "user"
    assert data["blocked_at"] is None
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_admin_create_user_4xx_duplicate_email(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    existing_email = f"existing-{uuid4()}@test.com"
    await _create_user(db_session, existing_email)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": existing_email, "password": "securepass1", "role": "user"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code in (400, 409)


@pytest.mark.asyncio
async def test_admin_create_user_422_short_password(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": f"u-{uuid4()}@test.com", "password": "short", "role": "user"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_create_user_403_non_admin(client: AsyncClient, db_session: AsyncSession):
    regular = await _create_user(db_session, f"user-{uuid4()}@test.com")
    await db_session.commit()

    resp = await client.post(
        "/api/v1/admin/users",
        json={"email": f"new-{uuid4()}@test.com", "password": "securepass1", "role": "user"},
        headers=_auth_headers(regular),
    )
    assert resp.status_code == 403


# ── PATCH /admin/users/{id} ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_update_user_200_email(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target = await _create_user(db_session, f"user-{uuid4()}@test.com")
    await db_session.commit()

    new_email = f"updated-{uuid4()}@test.com"
    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"email": new_email},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == new_email


@pytest.mark.asyncio
async def test_admin_update_user_200_role(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target = await _create_user(db_session, f"user-{uuid4()}@test.com", UserRole.user)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"role": "administrator"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "administrator"


@pytest.mark.asyncio
async def test_admin_update_self_role_403(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"role": "user"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_self_email_403(client: AsyncClient, db_session: AsyncSession):
    # update_user blocks ALL self-edits (not just role changes) per T030 Major fix.
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"email": f"newemail-{uuid4()}@test.com"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_user_403_non_admin(client: AsyncClient, db_session: AsyncSession):
    regular = await _create_user(db_session, f"user-{uuid4()}@test.com")
    target = await _create_user(db_session, f"other-{uuid4()}@test.com")
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"role": "administrator"},
        headers=_auth_headers(regular),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_update_user_404(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/admin/users/{uuid4()}",
        json={"email": "x@test.com"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_update_user_200_password_reset(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target_email = f"agent-{uuid4()}@agents.local"
    target = await _create_user(db_session, target_email)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"password": "newpassword99"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(target.id)
    assert data["email"] == target_email


@pytest.mark.asyncio
async def test_admin_password_reset_login_succeeds(client: AsyncClient, db_session: AsyncSession):
    """After a password reset via PATCH, the user can log in with the new password."""
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target_email = f"agent-{uuid4()}@agents.local"
    target = await _create_user(db_session, target_email)
    await db_session.commit()

    new_password = "resetpassword42"
    await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"password": new_password},
        headers=_auth_headers(admin),
    )

    login_resp = await client.post(
        "/api/v1/auth/token",
        json={"email": target_email, "password": new_password},
    )
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


@pytest.mark.asyncio
async def test_admin_update_user_422_short_password(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target = await _create_user(db_session, f"agent-{uuid4()}@agents.local")
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"password": "short"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_self_password_reset_403(client: AsyncClient, db_session: AsyncSession):
    """Admin cannot reset their own password via this endpoint (self-edit guard)."""
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"password": "newpassword99"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 403


# ── POST /admin/users/{id}/block ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_block_user_200(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target = await _create_user(db_session, f"user-{uuid4()}@test.com")
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/block",
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["blocked_at"] is not None
    assert data["id"] == str(target.id)


@pytest.mark.asyncio
async def test_admin_block_already_blocked_200_idempotent(
    client: AsyncClient, db_session: AsyncSession
):
    # openapi-admin.yaml: block is idempotent — second block of an already-blocked user returns 200.
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target = await _create_user(db_session, f"user-{uuid4()}@test.com")
    await db_session.commit()

    await client.post(f"/api/v1/admin/users/{target.id}/block", headers=_auth_headers(admin))
    resp = await client.post(f"/api/v1/admin/users/{target.id}/block", headers=_auth_headers(admin))
    assert resp.status_code == 200
    assert resp.json()["blocked_at"] is not None


@pytest.mark.asyncio
async def test_admin_block_self_403(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/users/{admin.id}/block",
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_block_user_403_non_admin(client: AsyncClient, db_session: AsyncSession):
    regular = await _create_user(db_session, f"user-{uuid4()}@test.com")
    target = await _create_user(db_session, f"other-{uuid4()}@test.com")
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/block",
        headers=_auth_headers(regular),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_block_user_404(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/users/{uuid4()}/block",
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 404


# ── POST /admin/users/{id}/unblock ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_unblock_user_200(client: AsyncClient, db_session: AsyncSession):
    from datetime import UTC, datetime

    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target = await _create_user(db_session, f"user-{uuid4()}@test.com")
    target.blocked_at = datetime.now(UTC)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/unblock",
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["blocked_at"] is None
    assert data["id"] == str(target.id)


@pytest.mark.asyncio
async def test_admin_unblock_already_active_200_idempotent(
    client: AsyncClient, db_session: AsyncSession
):
    # openapi-admin.yaml: unblock is idempotent — unblocking an already-active user returns 200.
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    target = await _create_user(db_session, f"user-{uuid4()}@test.com")
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/unblock",
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["blocked_at"] is None


@pytest.mark.asyncio
async def test_admin_unblock_user_403_non_admin(client: AsyncClient, db_session: AsyncSession):
    regular = await _create_user(db_session, f"user-{uuid4()}@test.com")
    target = await _create_user(db_session, f"other-{uuid4()}@test.com")
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/unblock",
        headers=_auth_headers(regular),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_unblock_user_404(client: AsyncClient, db_session: AsyncSession):
    admin = await _create_user(db_session, f"admin-{uuid4()}@test.com", UserRole.administrator)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/admin/users/{uuid4()}/unblock",
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 404
