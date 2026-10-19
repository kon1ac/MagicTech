#!/usr/bin/env bash
# Инкрементальный бэкап (каждые 4 часа). cron: 0 */4 * * * /path/scripts/backup_incremental.sh
# PostgreSQL 17+: pg_basebackup --incremental от предыдущего манифеста (нужен summarize_wal = on).
# Между копиями RPO ≤ 15 мин обеспечивает архив WAL (scripts/postgresql-wal.conf, archive_timeout = 900).
set -euo pipefail
DB_USER="${DB_USER:-postgres}"; DB_HOST="${DB_HOST:-localhost}"; DB_PORT="${DB_PORT:-5432}"
BASE_DIR="${MAGTECH_BASEBACKUP_DIR:-/var/backups/magictech/base}"
export PGPASSWORD="${DB_PASSWORD:-1}"
mkdir -p "$BASE_DIR"
STAMP=$(date +%Y%m%d_%H%M%S)
LAST=$(ls -1d "$BASE_DIR"/*/ 2>/dev/null | tail -n 1 || true)
if [[ -z "$LAST" || "$(date +%H)" == "02" ]]; then
  pg_basebackup -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -D "$BASE_DIR/full_$STAMP" -Fp -X stream -c fast
  echo "OK: base full_$STAMP"
else
  pg_basebackup -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -D "$BASE_DIR/incr_$STAMP" -Fp -X stream -c fast \
    --incremental="${LAST%/}/backup_manifest"
  echo "OK: incremental incr_$STAMP (от ${LAST%/})"
fi
# Восстановление цепочки: pg_combinebackup full_* incr_* ... -o /restore/dir
