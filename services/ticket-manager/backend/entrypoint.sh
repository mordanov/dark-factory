#!/bin/sh
set -e

# Acquire a PostgreSQL advisory lock (id=1) so only one replica runs migrations.
# All other replicas wait, then proceed once the lock is released.
python - <<'EOF'
import asyncio
from sqlalchemy import text
from src.core.database import engine

async def migrate():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT pg_advisory_lock(1)"))
        try:
            import subprocess
            result = subprocess.run(["alembic", "upgrade", "head"], check=True)
        finally:
            await conn.execute(text("SELECT pg_advisory_unlock(1)"))
        await conn.commit()

asyncio.run(migrate())
EOF

python -m src.core.seed

exec uvicorn src.main:app --host 0.0.0.0 --port 8000
