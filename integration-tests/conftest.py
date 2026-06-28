"""Integration test fixtures.

All HTTP clients are session-scoped (login once, reuse token).
conftest.py MUST NOT call any registration or user-creation API endpoint —
test users are provisioned by each service's startup seed script.
"""

from __future__ import annotations

import os

import httpx
import pytest_asyncio

# ── Service base URLs (override via env for custom environments) ────────────
UIM_BASE = os.getenv("UIM_BASE_URL", "http://user-input-manager:8000")
TM_BASE = os.getenv("TM_BASE_URL", "http://ticket-manager:8000")
ORCH_BASE = os.getenv("ORCH_BASE_URL", "http://orchestrator:8000")
DISTILLER_BASE = os.getenv("DISTILLER_BASE_URL", "http://context-distiller:8000")

# ── Test credentials (must match service seed env vars) ─────────────────────
UIM_ADMIN_EMAIL = os.getenv("UIM_ADMIN_EMAIL", "admin@uim.example.com")
UIM_ADMIN_PASSWORD = os.getenv("UIM_ADMIN_PASSWORD", "AdminPass123!")

TM_ADMIN_EMAIL = os.getenv("TM_ADMIN_EMAIL", "admin@tm.example.com")
TM_ADMIN_PASSWORD = os.getenv("TM_ADMIN_PASSWORD", "AdminPass123!")


@pytest_asyncio.fixture(scope="session")
async def uim_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=UIM_BASE, timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def tm_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=TM_BASE, timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def orch_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=ORCH_BASE, timeout=60.0) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def distiller_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=DISTILLER_BASE, timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def uim_auth_headers(uim_client: httpx.AsyncClient) -> dict[str, str]:
    resp = await uim_client.post(
        "/api/v1/auth/login",
        json={"email": UIM_ADMIN_EMAIL, "password": UIM_ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"UIM login failed: {resp.status_code} {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="session")
async def tm_auth_headers(tm_client: httpx.AsyncClient) -> dict[str, str]:
    resp = await tm_client.post(
        "/api/v1/auth/login",
        json={"email": TM_ADMIN_EMAIL, "password": TM_ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, f"TM login failed: {resp.status_code} {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
