"""
Dev seed script. Run from backend/ after alembic upgrade head.

Usage:
    python scripts/seed_dev.py

Creates (idempotent — skips records that already exist):
    - admin@example.com / admin123 (role: administrator)
    - user@example.com  / user123  (role: user)
    - 1 project: "Demo Project" (slug: demo-project)
    - 3 tickets in OPEN, IN_PROGRESS, IN_REVIEW statuses
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

import bcrypt

# Allow running from backend/ or repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on env vars

import asyncpg  # type: ignore[import]

DATABASE_URL = os.environ.get("DATABASE_URL", "")


# asyncpg uses postgresql:// not postgresql+asyncpg://
def _asyncpg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
TICKET_OPEN_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")
TICKET_IP_ID = uuid.UUID("00000000-0000-0000-0000-000000000102")
TICKET_IR_ID = uuid.UUID("00000000-0000-0000-0000-000000000103")


async def seed() -> None:
    if not DATABASE_URL:
        sys.exit("ERROR: DATABASE_URL environment variable is not set.")

    conn = await asyncpg.connect(_asyncpg_url(DATABASE_URL))
    try:
        async with conn.transaction():
            # --- Users ---
            await conn.execute(
                """
                INSERT INTO users (id, email, hashed_password, role)
                VALUES ($1, $2, $3, 'administrator')
                ON CONFLICT (email) DO NOTHING
                """,
                ADMIN_ID,
                "admin@example.com",
                _hash("admin123"),
            )
            await conn.execute(
                """
                INSERT INTO users (id, email, hashed_password, role)
                VALUES ($1, $2, $3, 'user')
                ON CONFLICT (email) DO NOTHING
                """,
                USER_ID,
                "user@example.com",
                _hash("user123"),
            )

            # --- Project ---
            await conn.execute(
                """
                INSERT INTO projects (id, name, slug, code, created_by)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (slug) DO NOTHING
                """,
                PROJECT_ID,
                "Demo Project",
                "demo-project",
                "DEMO-001",
                ADMIN_ID,
            )

            # --- Tickets ---
            tickets = [
                (
                    TICKET_OPEN_ID,
                    "Set up repository",
                    "Initialize the project repository and CI pipeline.",
                    "OPEN",
                ),
                (
                    TICKET_IP_ID,
                    "Implement auth endpoints",
                    "Build login, logout, and token refresh endpoints.",
                    "IN_PROGRESS",
                ),
                (
                    TICKET_IR_ID,
                    "Add ticket list view",
                    "Create the project ticket list page in the frontend.",
                    "IN_REVIEW",
                ),
            ]
            for tid, title, description, status in tickets:
                await conn.execute(
                    """
                    INSERT INTO tickets (id, project_id, parent_ticket_id, title, description, status, created_by)
                    VALUES ($1, $2, NULL, $3, $4, $5, $6)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    tid,
                    PROJECT_ID,
                    title,
                    description,
                    status,
                    ADMIN_ID,
                )

        print("Seed complete.")
        print("  admin@example.com / admin123  (administrator)")
        print("  user@example.com  / user123   (user)")
        print(f"  Project ID : {PROJECT_ID}")
        print(f"  Ticket IDs : {TICKET_OPEN_ID} (OPEN)")
        print(f"             : {TICKET_IP_ID} (IN_PROGRESS)")
        print(f"             : {TICKET_IR_ID} (IN_REVIEW)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
