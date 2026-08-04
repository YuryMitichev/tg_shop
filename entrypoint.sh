#!/bin/sh
set -e

if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q "postgresql"; then
    echo "Waiting for PostgreSQL..."
    until python -c "import asyncio; import asyncpg; asyncio.run(asyncpg.connect('host=postgres port=5432 user=tg_shop password=${POSTGRES_PASSWORD:-changeme} database=tg_shop'))" 2>/dev/null; do
        echo "  PostgreSQL not ready, retrying in 2s..."
        sleep 2
    done
    echo "PostgreSQL is ready."
fi

echo "Running database migrations..."
alembic upgrade head

echo "Starting bot..."
exec python run.py
