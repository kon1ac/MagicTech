#!/usr/bin/env bash
# Восстановление из логической копии. Пример проверки на тестовом контуре:
#   TARGET_DB=MagicTech_restore_test ./scripts/restore.sh backups/MagicTech_full_20261019_020000.dump
# Восстановление боевой БД (RTO ≤ 1 ч): остановить приложение, затем TARGET_DB=MagicTech ./scripts/restore.sh <файл>
set -euo pipefail
FILE="${1:?Укажите файл .dump}"
TARGET_DB="${TARGET_DB:-MagicTech_restore_test}"; DB_USER="${DB_USER:-postgres}"; DB_HOST="${DB_HOST:-localhost}"; DB_PORT="${DB_PORT:-5432}"
export PGPASSWORD="${DB_PASSWORD:-1}"
[[ -f "$FILE.sha256" ]] && sha256sum -c "$FILE.sha256"
START=$(date +%s)
if [[ "$TARGET_DB" == *_restore_test ]]; then
  dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" --if-exists "$TARGET_DB"
  createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$TARGET_DB"
  pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" --no-owner -j 4 "$FILE"
else
  pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" --clean --if-exists --no-owner --single-transaction "$FILE"
fi
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$TARGET_DB" -tAc \
  "SELECT 'orders='||count(*) FROM orders UNION ALL SELECT 'products='||count(*) FROM products UNION ALL SELECT 'payments='||count(*) FROM payments"
echo "Восстановлено в $TARGET_DB за $(( $(date +%s) - START )) с"
