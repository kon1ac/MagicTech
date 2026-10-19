#!/usr/bin/env bash
# Полный бэкап БД MagicTech (ночное окно). cron: 0 2 * * * /path/scripts/backup_full.sh
set -euo pipefail
DB_NAME="${DB_NAME:-MagicTech}"; DB_USER="${DB_USER:-postgres}"; DB_HOST="${DB_HOST:-localhost}"; DB_PORT="${DB_PORT:-5432}"
BACKUP_DIR="${MAGTECH_BACKUP_DIR:-$(dirname "$0")/../backups}"; KEEP_DAYS="${KEEP_DAYS:-30}"
export PGPASSWORD="${DB_PASSWORD:-1}"
mkdir -p "$BACKUP_DIR"
FILE="$BACKUP_DIR/${DB_NAME}_full_$(date +%Y%m%d_%H%M%S).dump"
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -F c -Z 6 -f "$FILE"
sha256sum "$FILE" > "$FILE.sha256"
pg_restore --list "$FILE" > /dev/null   # быстрая проверка целостности архива
find "$BACKUP_DIR" -name "${DB_NAME}_*.dump*" -mtime +"$KEEP_DAYS" -delete   # ротация ≥ 30 дней
echo "OK: $FILE ($(du -h "$FILE" | cut -f1))"
