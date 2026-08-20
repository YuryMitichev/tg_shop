#!/bin/sh
set -e

if [ -n "$DATABASE_URL" ] && echo "$DATABASE_URL" | grep -q "postgresql"; then
    case "${POSTGRES_PASSWORD:-}" in
        ""|changeme|password|postgres|tg_shop)
            echo "ERROR: set a strong POSTGRES_PASSWORD (at least 16 characters)." >&2
            exit 1
            ;;
    esac
    if [ "${#POSTGRES_PASSWORD}" -lt 16 ]; then
        echo "ERROR: POSTGRES_PASSWORD must contain at least 16 characters." >&2
        exit 1
    fi
    echo "Waiting for PostgreSQL..."
    until python -c "
import asyncio, asyncpg, os
dsn = os.environ['DATABASE_URL'].replace('+asyncpg', '')
asyncio.run(asyncpg.connect(dsn))
" 2>/dev/null; do
        echo "  PostgreSQL not ready, retrying in 2s..."
        sleep 2
    done
    echo "PostgreSQL is ready."
fi

echo "Running database migrations..."
alembic upgrade head

echo "Starting bot..."
exec python run.py
