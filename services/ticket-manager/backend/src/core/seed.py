"""Seed module — no-op after Keycloak migration.

User management is now handled by Keycloak; no local user seeding required.
"""


async def seed_default_users() -> None:
    pass
