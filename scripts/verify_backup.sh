#!/bin/sh
set -eu

RESTORE_CONTAINER="tg_shop_restore_check_$(date +%s)"
RESTORE_DATABASE="tg_shop_restore"
RESTORE_PASSWORD="restore_check_only"

cleanup() {
    docker rm -f "${RESTORE_CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

if docker ps -a --format '{{.Names}}' | grep -qx "${RESTORE_CONTAINER}"; then
    echo "Temporary restore container already exists" >&2
    exit 1
fi

LATEST_BACKUP=$(docker compose exec -T backup sh -c \
    'ls -1t /backups/daily/*.sql.gz 2>/dev/null | head -n 1')
if [ -z "${LATEST_BACKUP}" ]; then
    echo "No daily backup found" >&2
    exit 1
fi

docker run -d --rm \
    --name "${RESTORE_CONTAINER}" \
    -e POSTGRES_PASSWORD="${RESTORE_PASSWORD}" \
    -e POSTGRES_DB="${RESTORE_DATABASE}" \
    postgres:16-alpine >/dev/null

ready=false
attempt=1
while [ "${attempt}" -le 20 ]; do
    if docker exec "${RESTORE_CONTAINER}" \
        pg_isready -U postgres -d "${RESTORE_DATABASE}" >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 1
    attempt=$((attempt + 1))
done

if [ "${ready}" != "true" ]; then
    echo "Temporary PostgreSQL did not become ready" >&2
    exit 1
fi

docker compose exec -T backup gzip -dc "${LATEST_BACKUP}" | \
    docker exec -i "${RESTORE_CONTAINER}" \
        psql -v ON_ERROR_STOP=1 -U postgres -d "${RESTORE_DATABASE}" >/dev/null

TABLE_COUNT=$(docker exec "${RESTORE_CONTAINER}" \
    psql -At -U postgres -d "${RESTORE_DATABASE}" \
    -c "select count(*) from information_schema.tables where table_schema = 'public';")

if [ "${TABLE_COUNT}" -le 0 ]; then
    echo "Restore validation failed: no public tables" >&2
    exit 1
fi

echo "Restore verification passed: ${TABLE_COUNT} public tables"
