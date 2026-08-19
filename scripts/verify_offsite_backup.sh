#!/bin/sh
set -eu

umask 077

YANDEX_STORAGE_ENDPOINT="${YANDEX_STORAGE_ENDPOINT:-https://storage.yandexcloud.net}"
TEMP_ENCRYPTED="/tmp/offsite-backup-verify.enc"
TEMP_GZIP="/tmp/offsite-backup-verify.sql.gz"
TEMP_SQL="/tmp/offsite-backup-verify.sql"

cleanup() {
    rm -f "${TEMP_ENCRYPTED}" "${TEMP_GZIP}" "${TEMP_SQL}"
}
trap cleanup EXIT HUP INT TERM

if [ -z "${YANDEX_BACKUP_BUCKET:-}" ] || [ -z "${AWS_ACCESS_KEY_ID:-}" ] || \
   [ -z "${AWS_SECRET_ACCESS_KEY:-}" ] || [ -z "${BACKUP_ENCRYPTION_PASSPHRASE:-}" ]; then
    echo "Off-site backup configuration is incomplete" >&2
    exit 1
fi

object_key=$(aws s3api list-objects-v2 \
    --endpoint-url "${YANDEX_STORAGE_ENDPOINT}" \
    --bucket "${YANDEX_BACKUP_BUCKET}" \
    --prefix database/ \
    --query 'sort_by(Contents,&LastModified)[-1].Key' \
    --output text)

if [ -z "${object_key}" ] || [ "${object_key}" = "None" ]; then
    echo "No off-site database backups found" >&2
    exit 1
fi

aws s3api get-object \
    --endpoint-url "${YANDEX_STORAGE_ENDPOINT}" \
    --bucket "${YANDEX_BACKUP_BUCKET}" \
    --key "${object_key}" \
    "${TEMP_ENCRYPTED}" >/dev/null

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
    -in "${TEMP_ENCRYPTED}" -out "${TEMP_GZIP}" \
    -pass env:BACKUP_ENCRYPTION_PASSPHRASE
gzip -t "${TEMP_GZIP}"
gzip -cd "${TEMP_GZIP}" > "${TEMP_SQL}"

if [ ! -s "${TEMP_SQL}" ] || ! grep -q '^-- PostgreSQL database dump complete' "${TEMP_SQL}"; then
    echo "Downloaded off-site backup is incomplete" >&2
    exit 1
fi

echo "Off-site backup download and decryption verification passed."
