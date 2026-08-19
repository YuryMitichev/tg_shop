#!/bin/sh
set -eu

umask 077

DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-tg_shop}"
DB_USER="${DB_USER:-tg_shop}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_MAX_ATTEMPTS="${BACKUP_MAX_ATTEMPTS:-3}"
BACKUP_RETRY_DELAY="${BACKUP_RETRY_DELAY:-10}"
YANDEX_BACKUP_ENABLED="${YANDEX_BACKUP_ENABLED:-false}"
YANDEX_BACKUP_BUCKET="${YANDEX_BACKUP_BUCKET:-}"
YANDEX_STORAGE_ENDPOINT="${YANDEX_STORAGE_ENDPOINT:-https://storage.yandexcloud.net}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DAILY_DIR="${BACKUP_DIR}/daily"
WEEKLY_DIR="${BACKUP_DIR}/weekly"
DUMP_FILE="${DAILY_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"
TEMP_SQL="${DAILY_DIR}/.${DB_NAME}_${TIMESTAMP}.sql.tmp"
TEMP_GZIP="${DUMP_FILE}.tmp"
SUCCESS_FILE="${BACKUP_DIR}/last_success"
WEEKLY_TEMP=""
ENCRYPTED_TEMP=""

mkdir -p "${DAILY_DIR}" "${WEEKLY_DIR}"

cleanup() {
    rm -f "${TEMP_SQL}" "${TEMP_GZIP}" "${SUCCESS_FILE}.tmp"
    if [ -n "${WEEKLY_TEMP}" ]; then
        rm -f "${WEEKLY_TEMP}"
    fi
    if [ -n "${ENCRYPTED_TEMP}" ]; then
        rm -f "${ENCRYPTED_TEMP}"
    fi
}
trap cleanup EXIT HUP INT TERM

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup..."

attempt=1
while :; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] pg_dump attempt ${attempt}/${BACKUP_MAX_ATTEMPTS}"
    if pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
        --no-owner --no-privileges > "${TEMP_SQL}"; then
        break
    fi

    rm -f "${TEMP_SQL}"
    if [ "${attempt}" -ge "${BACKUP_MAX_ATTEMPTS}" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup failed after ${attempt} attempts" >&2
        exit 1
    fi

    sleep $((BACKUP_RETRY_DELAY * attempt))
    attempt=$((attempt + 1))
done

if [ ! -s "${TEMP_SQL}" ] || ! grep -q '^-- PostgreSQL database dump complete' "${TEMP_SQL}"; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup validation failed: incomplete SQL dump" >&2
    exit 1
fi

gzip -c "${TEMP_SQL}" > "${TEMP_GZIP}"
gzip -t "${TEMP_GZIP}"
mv "${TEMP_GZIP}" "${DUMP_FILE}"
rm -f "${TEMP_SQL}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup created: ${DUMP_FILE} ($(du -h "${DUMP_FILE}" | cut -f1))"

# Rotation daily: keep last 7.
cd "${DAILY_DIR}"
ls -1t ./*.sql.gz 2>/dev/null | tail -n +8 | while read -r file; do
    rm -f -- "${file}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Removed old daily backup: ${file#./}"
done

# Weekly backup on Sundays.
if [ "$(date +%u)" = "7" ]; then
    WEEKLY_FILE="${WEEKLY_DIR}/${DB_NAME}_$(date +%Y%m%d).sql.gz"
    WEEKLY_TEMP="${WEEKLY_FILE}.tmp"
    cp "${DUMP_FILE}" "${WEEKLY_TEMP}"
    gzip -t "${WEEKLY_TEMP}"
    mv "${WEEKLY_TEMP}" "${WEEKLY_FILE}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Weekly snapshot: ${WEEKLY_FILE}"

    cd "${WEEKLY_DIR}"
    ls -1t ./*.sql.gz 2>/dev/null | tail -n +5 | while read -r file; do
        rm -f -- "${file}"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Removed old weekly backup: ${file#./}"
    done
fi

upload_to_yandex() {
    if [ "${YANDEX_BACKUP_ENABLED}" != "true" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Off-site backup is disabled."
        return
    fi

    if [ -z "${YANDEX_BACKUP_BUCKET}" ] || [ -z "${AWS_ACCESS_KEY_ID:-}" ] || \
       [ -z "${AWS_SECRET_ACCESS_KEY:-}" ] || [ -z "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Off-site backup configuration is incomplete" >&2
        exit 1
    fi

    object_key="database/${DB_NAME}_${TIMESTAMP}.sql.gz.enc"
    ENCRYPTED_TEMP="${DUMP_FILE}.enc.tmp"

    openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
        -in "${DUMP_FILE}" -out "${ENCRYPTED_TEMP}" \
        -pass env:BACKUP_ENCRYPTION_PASSPHRASE

    content_md5=$(openssl dgst -md5 -binary "${ENCRYPTED_TEMP}" | openssl base64 -A)
    aws s3api put-object \
        --endpoint-url "${YANDEX_STORAGE_ENDPOINT}" \
        --bucket "${YANDEX_BACKUP_BUCKET}" \
        --key "${object_key}" \
        --body "${ENCRYPTED_TEMP}" \
        --content-md5 "${content_md5}" >/dev/null

    remote_size=$(aws s3api head-object \
        --endpoint-url "${YANDEX_STORAGE_ENDPOINT}" \
        --bucket "${YANDEX_BACKUP_BUCKET}" \
        --key "${object_key}" \
        --query ContentLength --output text)
    local_size=$(wc -c < "${ENCRYPTED_TEMP}" | tr -d ' ')

    if [ "${remote_size}" != "${local_size}" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Off-site backup size verification failed" >&2
        exit 1
    fi

    rm -f "${ENCRYPTED_TEMP}"
    ENCRYPTED_TEMP=""
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Encrypted off-site backup uploaded and verified."
}

upload_to_yandex

date +%s > "${SUCCESS_FILE}.tmp"
mv "${SUCCESS_FILE}.tmp" "${SUCCESS_FILE}"
trap - EXIT HUP INT TERM

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup complete."
