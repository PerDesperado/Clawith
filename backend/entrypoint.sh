#!/bin/sh
# Docker entrypoint: run DB migrations, then start the app.
set -e

echo "[entrypoint] Checking migration state..."

# If alembic_version table doesn't exist (manual installs) stamp head so we don't
# re-run migrations that were already applied outside of Alembic.
python3 -c "
import asyncio, os, sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        return False
    # Ensure async driver
    url = url.replace('postgresql://', 'postgresql+asyncpg://').replace('postgres://', 'postgresql+asyncpg://')
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            r = await conn.execute(text(\"SELECT to_regclass('public.alembic_version')\"))
            tbl = r.scalar()
            return tbl is not None
    except Exception as e:
        print(f'DB check failed: {e}', file=sys.stderr)
        return False

result = asyncio.run(main())
sys.exit(0 if result else 1)
" && echo "[entrypoint] alembic_version found — upgrading normally..." \
  || (echo "[entrypoint] No alembic_version — stamping head to skip pre-existing tables..." && alembic stamp head)

echo "[entrypoint] Running alembic upgrade head..."
alembic upgrade head

echo "[entrypoint] Migrations done — starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
