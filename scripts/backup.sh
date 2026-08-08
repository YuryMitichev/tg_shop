#!/bin/sh
set -e

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-tg_shop}"
DB_USER="${DB_USER:-tg_shop}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DAILY_DIR="${BACKUP_DIR}/daily"
WEEKLY_DIR="${BACKUP_DIR}/weekly"
DUMP_FILE="${DAILY_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

mkdir -p "${DAILY_DIR}" "${WEEKLY_DIR}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup..."

pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    --no-owner --no-privileges | gzip > "${DUMP_FILE}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup created: ${DUMP_FILE} ($(du -h "${DUMP_FILE}" | cut -f1))"

# Rotation daily: keep last 7
cd "${DAILY_DIR}" && ls -1t *.sql.gz 2>/dev/null | tail -n +8 | while read -r f; do
    rm -f "${DAILY_DIR}/${f}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Removed old daily backup: ${f}"
done

# Weekly backup on Sundays
DAY_OF_WEEK=$(date +%u)
if [ "${DAY_OF_WEEK}" = "7" ]; then
    WEEKLY_FILE="${WEEKLY_DIR}/${DB_NAME}_$(date +%Y%m%d).sql.gz"
    cp "${DUMP_FILE}" "${WEEKLY_FILE}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Weekly snapshot: ${WEEKLY_FILE}"

    # Rotation weekly: keep last 4
    cd "${WEEKLY_DIR}" && ls -1t *.sql.gz 2>/dev/null | tail -n +5 | while read -r f; do
        rm -f "${WEEKLY_DIR}/${f}"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Removed old weekly backup: ${f}"
    done
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup complete."
