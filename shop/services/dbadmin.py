"""Инфраструктурный контур данных: характеристики БД, индексы, права, бэкапы/restore,
регламентные задания, архивация устаревших данных."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.forms.models import model_to_dict
from django.utils import timezone

from shop.models import ArchivedOrder, ArchiveAccessGrant, BackupRecord, Order, ScheduledJob
from shop.services.audit import write_audit

# Таблицы с персональными данными пользователей ИС и где лежат файлы
USER_DATA_MAP = [
    ('auth_credentials', 'email, password_hash (Argon2), user_role', 'Учётные данные'),
    ('user_profiles', 'ФИО, телефон, адрес, аватар', 'Профиль; файлы аватаров — MEDIA_ROOT/avatars/'),
    ('user_settings', 'тема, язык, форматы, фильтры', 'Пользовательские настройки'),
    ('orders', 'адрес доставки, телефон, комментарий', 'Заказы покупателя'),
    ('payments / payment_logs', 'реквизиты карты (маска), ответы шлюза', 'Платёжные данные'),
    ('returns', 'описание претензии, фото', 'Фото — MEDIA_ROOT/returns/'),
    ('reviews', 'тексты, фото', 'Фото — MEDIA_ROOT/reviews/'),
    ('audit_log', 'IP, User-Agent', 'Журнал аудита'),
    ('orders_archive', 'JSON-снимки заказов', 'Архив устаревших данных'),
]

TRANSACTIONAL_TABLES = ['orders', 'order_items', 'payments', 'payment_logs', 'returns', 'return_items',
                        'reservations', 'stock', 'stock_movements', 'carts', 'cart_items', 'audit_log']
REFERENCE_TABLES = ['categories', 'brands', 'units', 'characteristics', 'order_statuses', 'return_reasons',
                    'promotion_types', 'promotions', 'promotion_products', 'promotion_categories',
                    'promotion_brands', 'db_jobs', 'django_migrations']


def is_postgres() -> bool:
    return connection.vendor == 'postgresql'


def _fetch(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        cols = [c[0] for c in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


def db_characteristics() -> dict:
    db = settings.DATABASES['default']
    info = {
        'vendor': connection.vendor, 'name': str(db['NAME']), 'host': db.get('HOST') or 'local',
        'port': db.get('PORT') or '', 'user': db.get('USER') or '',
        'media_root': str(settings.MEDIA_ROOT), 'backup_dir': str(settings.MAGTECH_BACKUP_DIR),
    }
    if not is_postgres():
        info['version'] = 'SQLite (режим разработки)'
        info['tables'] = [{'table': t} for t in connection.introspection.table_names()]
        return info
    info['version'] = _fetch('SELECT version() AS v')[0]['v']
    info.update(_fetch("""
        SELECT pg_size_pretty(pg_database_size(current_database())) AS size,
               (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS connections,
               current_setting('max_connections') AS max_connections,
               current_setting('shared_buffers') AS shared_buffers,
               current_setting('work_mem') AS work_mem,
               current_setting('server_encoding') AS encoding,
               current_setting('TimeZone') AS timezone,
               current_setting('wal_level') AS wal_level,
               current_setting('archive_mode') AS archive_mode,
               current_setting('data_directory', true) AS data_directory,
               pg_postmaster_start_time() AS started_at,
               (SELECT round(100.0 * sum(blks_hit) / nullif(sum(blks_hit) + sum(blks_read), 0), 2)
                  FROM pg_stat_database WHERE datname = current_database()) AS cache_hit_ratio
    """)[0])
    info['tables'] = _fetch("""
        SELECT c.relname AS table, c.reltuples::bigint AS rows_estimate,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
               pg_size_pretty(pg_indexes_size(c.oid)) AS index_size,
               s.seq_scan, s.idx_scan, s.n_dead_tup, s.last_autovacuum, s.last_analyze
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
          LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
         WHERE n.nspname = 'public' AND c.relkind = 'r'
         ORDER BY pg_total_relation_size(c.oid) DESC
    """)
    return info


def indexes() -> list[dict]:
    if not is_postgres():
        return []
    return _fetch("""
        SELECT i.tablename AS table, i.indexname AS index, i.indexdef AS definition,
               pg_size_pretty(pg_relation_size(format('%%I.%%I', i.schemaname, i.indexname)::regclass)) AS size,
               COALESCE(s.idx_scan, 0) AS scans
          FROM pg_indexes i
          LEFT JOIN pg_stat_user_indexes s ON s.indexrelname = i.indexname AND s.schemaname = i.schemaname
         WHERE i.schemaname = 'public'
         ORDER BY i.tablename, i.indexname
    """)


def slow_queries() -> list[dict]:
    """Требует расширения pg_stat_statements; если его нет — пустой список."""
    if not is_postgres():
        return []
    try:
        with transaction.atomic():
            return _fetch("""
                SELECT left(query, 200) AS query, calls, round(mean_exec_time::numeric, 2) AS mean_ms,
                       round(total_exec_time::numeric, 2) AS total_ms
                  FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 15
            """)
    except Exception:
        return []


def roles_and_grants() -> dict:
    if not is_postgres():
        return {'roles': [], 'grants': []}
    roles = _fetch("""
        SELECT rolname AS role, rolsuper AS superuser, rolcreatedb AS createdb, rolcanlogin AS login,
               rolconnlimit AS conn_limit, rolvaliduntil AS valid_until
          FROM pg_roles WHERE rolname NOT LIKE 'pg\\_%%' ORDER BY rolname
    """)
    grants = _fetch("""
        SELECT grantee, string_agg(DISTINCT privilege_type, ', ' ORDER BY privilege_type) AS privileges,
               count(DISTINCT table_name) AS tables
          FROM information_schema.role_table_grants WHERE table_schema = 'public'
         GROUP BY grantee ORDER BY grantee
    """)
    return {'roles': roles, 'grants': grants}


def migrations_state() -> list[dict]:
    executor = MigrationExecutor(connection)
    applied = executor.loader.applied_migrations
    result = []
    for (app, name) in sorted(executor.loader.graph.nodes):
        if app in {'users', 'shop', 'admin', 'auth', 'contenttypes', 'sessions'}:
            record = applied.get((app, name))
            result.append({'app': app, 'name': name, 'applied': (app, name) in applied,
                           'applied_at': getattr(record, 'applied', None)})
    return result


# ---------------------------------------------------------------- бэкапы

def _pg_bin(name: str) -> str:
    pg_bin = os.environ.get('PG_BIN')
    if pg_bin:
        candidate = Path(pg_bin) / (name + ('.exe' if os.name == 'nt' else ''))
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise ValidationError(f'Не найдена утилита {name}. Установите клиент PostgreSQL или задайте PG_BIN.')
    return found


def _pg_env():
    db = settings.DATABASES['default']
    env = os.environ.copy()
    env['PGPASSWORD'] = str(db.get('PASSWORD') or '')
    return env, ['-h', db.get('HOST') or 'localhost', '-p', str(db.get('PORT') or 5432), '-U', db.get('USER') or 'postgres']


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def create_backup(kind: str = 'full', *, actor=None, request=None) -> BackupRecord:
    """full — вся БД; incremental — транзакционные таблицы (между полными копиями, каждые 4 ч);
    schema — схема + справочники/конфигурации (при релизе/изменении схемы).
    Для RPO ≤ 15 мин дополнительно включается архивирование WAL (см. scripts/postgresql-wal.conf)."""
    if not is_postgres():
        raise ValidationError('Резервное копирование доступно только для PostgreSQL.')
    if kind not in {'full', 'incremental', 'schema'}:
        raise ValidationError('Неизвестный тип копии.')
    backup_dir = Path(settings.MAGTECH_BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    db = settings.DATABASES['default']
    stamp = timezone.localtime().strftime('%Y%m%d_%H%M%S')
    path = backup_dir / f'{db["NAME"]}_{kind}_{stamp}.dump'
    env, conn = _pg_env()
    cmd = [_pg_bin('pg_dump'), *conn, '-d', db['NAME'], '-F', 'c', '-f', str(path)]
    if kind == 'incremental':
        for table in TRANSACTIONAL_TABLES:
            cmd += ['-t', table]
    elif kind == 'schema':
        cmd += ['--schema-only']
    record = BackupRecord(backup_kind=kind, file_path=str(path), id_user=actor)
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=3600)
        if kind == 'schema' and proc.returncode == 0:
            data_path = backup_dir / f'{db["NAME"]}_refdata_{stamp}.dump'
            ref = [_pg_bin('pg_dump'), *conn, '-d', db['NAME'], '-F', 'c', '--data-only', '-f', str(data_path)]
            for table in REFERENCE_TABLES:
                ref += ['-t', table]
            proc2 = subprocess.run(ref, env=env, capture_output=True, text=True, timeout=3600)
            proc = proc if proc2.returncode == 0 else proc2
        record.backup_status = 'success' if proc.returncode == 0 else 'failed'
        record.backup_output = (proc.stderr or proc.stdout or '')[-4000:]
    except (subprocess.TimeoutExpired, OSError) as exc:
        record.backup_status, record.backup_output = 'failed', str(exc)
    if record.backup_status == 'success' and path.exists():
        record.file_size = path.stat().st_size
        record.checksum = _sha256(path)
    record.save()
    write_audit(user=actor, object_type='backup', object_id=record.pk, action=f'create_{kind}',
                after={'status': record.backup_status, 'file': path.name, 'size': record.file_size}, request=request)
    return record


def verify_backup(record: BackupRecord, *, actor=None, full_restore: bool = True, request=None) -> BackupRecord:
    """Проверка restore на тестовом контуре: контрольная сумма + pg_restore в отдельную БД
    <имя>_restore_test и сверка числа таблиц."""
    path = Path(record.file_path)
    ok, notes = True, []
    if not path.exists():
        ok, notes = False, ['Файл копии не найден']
    elif record.checksum and _sha256(path) != record.checksum:
        ok, notes = False, ['Контрольная сумма не совпадает — файл повреждён']
    else:
        env, conn = _pg_env()
        listing = subprocess.run([_pg_bin('pg_restore'), '--list', str(path)], capture_output=True, text=True)
        if listing.returncode != 0:
            ok, notes = False, [listing.stderr[-1000:]]
        else:
            notes.append(f'Оглавление архива: {listing.stdout.count(chr(10))} объектов')
        if ok and full_restore:
            test_db = f'{settings.DATABASES["default"]["NAME"]}_restore_test'
            subprocess.run([_pg_bin('dropdb'), *conn, '--if-exists', test_db], env=env, capture_output=True)
            created = subprocess.run([_pg_bin('createdb'), *conn, test_db], env=env, capture_output=True, text=True)
            restored = subprocess.run([_pg_bin('pg_restore'), *conn, '-d', test_db, '--no-owner', str(path)],
                                      env=env, capture_output=True, text=True, timeout=3600)
            if created.returncode != 0 or restored.returncode not in (0, 1):
                ok = False
                notes.append((created.stderr or restored.stderr)[-1000:])
            else:
                count = subprocess.run(
                    [_pg_bin('psql'), *conn, '-d', test_db, '-tAc',
                     "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"],
                    env=env, capture_output=True, text=True)
                notes.append(f'Восстановлено в {test_db}: таблиц {count.stdout.strip() or "?"}')
                if restored.stderr.strip():
                    notes.append('Предупреждения pg_restore: ' + restored.stderr[-500:])
    record.verified_at = timezone.now()
    record.verify_status = 'ok' if ok else 'failed'
    record.backup_output = ((record.backup_output or '') + '\n[verify] ' + '\n'.join(notes))[-4000:]
    record.save()
    write_audit(user=actor, object_type='backup', object_id=record.pk, action='verify',
                after={'status': record.verify_status, 'notes': notes}, request=request)
    return record


def restore_backup(record: BackupRecord, *, actor, confirm_name: str, request=None) -> BackupRecord:
    """Восстановление рабочей БД из копии. Критическая операция: нужно ввести имя БД."""
    db_name = settings.DATABASES['default']['NAME']
    if confirm_name != db_name:
        raise ValidationError('Для подтверждения введите точное имя базы данных.')
    path = Path(record.file_path)
    if not path.exists():
        raise ValidationError('Файл копии не найден.')
    if record.checksum and _sha256(path) != record.checksum:
        raise ValidationError('Контрольная сумма не совпадает — восстановление запрещено.')
    write_audit(user=actor, object_type='backup', object_id=record.pk, action='restore_started',
                after={'file': path.name}, request=request)
    env, conn = _pg_env()
    connection.close()
    proc = subprocess.run([_pg_bin('pg_restore'), *conn, '-d', db_name, '--clean', '--if-exists', '--no-owner',
                           '--single-transaction', str(path)], env=env, capture_output=True, text=True, timeout=3600)
    record.refresh_from_db()
    record.restored_at = timezone.now()
    record.backup_output = ((record.backup_output or '') + '\n[restore] ' + (proc.stderr or 'OK'))[-4000:]
    record.save()
    write_audit(user=actor, object_type='backup', object_id=record.pk,
                action='restore_ok' if proc.returncode == 0 else 'restore_failed',
                after={'returncode': proc.returncode}, request=request)
    if proc.returncode != 0:
        raise ValidationError('pg_restore завершился с ошибкой: ' + proc.stderr[-500:])
    return record


def cleanup_old_backups(keep_days: int = 30) -> int:
    """Ротация: копии старше keep_days удаляются (последняя полная проверенная — сохраняется всегда)."""
    cutoff = timezone.now() - timedelta(days=keep_days)
    keep = BackupRecord.objects.filter(backup_kind='full', verify_status='ok').order_by('-created_at').first()
    removed = 0
    for record in BackupRecord.objects.filter(created_at__lt=cutoff).exclude(pk=getattr(keep, 'pk', None)):
        Path(record.file_path).unlink(missing_ok=True)
        record.delete()
        removed += 1
    return removed


def vacuum_analyze() -> str:
    if not is_postgres():
        return 'skip (не PostgreSQL)'
    with connection.cursor() as cursor:
        cursor.execute('VACUUM (ANALYZE)')
    return 'VACUUM ANALYZE выполнен'


# ---------------------------------------------------------------- архивация

def _order_snapshot(order: Order) -> dict:
    import json

    data = {
        'order': model_to_dict(order),
        'customer': order.id_user.email,
        'items': [model_to_dict(i) | {'sku': i.id_product.product_sku, 'name': i.id_product.product_name}
                  for i in order.items.select_related('id_product')],
        'payments': [model_to_dict(p) | {'payment_uid': str(p.payment_uid)} for p in order.payments.all()],
        'returns': [model_to_dict(r, exclude=['return_photo']) for r in order.returns.all()],
        'created_at': order.created_at,
    }
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


@transaction.atomic
def archive_old_orders(days: int | None = None, *, actor=None, request=None, limit: int = 5000) -> int:
    """Переносит закрытые заказы старше N дней в orders_archive (JSON-снимок) и удаляет из рабочих таблиц."""
    days = days or settings.MAGTECH_ARCHIVE_AFTER_DAYS
    cutoff = timezone.now() - timedelta(days=days)
    qs = Order.objects.filter(order_status__in=['COMPLETED', 'CANCELLED', 'RETURNED'], updated_at__lt=cutoff)
    count = 0
    for order in qs.select_related('id_user')[:limit]:
        ArchivedOrder.objects.create(
            original_order_id=order.pk, order_number=order.order_number, customer_email=order.id_user.email,
            order_total=order.total, order_created_at=order.created_at, archive_payload=_order_snapshot(order),
            archived_by=actor,
        )
        order.stock_movements.update(id_order=None)
        for ret in order.returns.all():
            ret.items.all().delete()
        order.returns.all().delete()
        order.reviews.update(id_order=None)
        order.items.all().delete()
        order.delete()
        count += 1
    write_audit(user=actor, object_type='archive', object_id=None, action='archive_orders',
                after={'archived': count, 'older_than_days': days}, request=request)
    return count


def has_archive_access(user) -> bool:
    from users.constants import ROLE_DB_ADMIN, ROLE_ADMIN

    if user.user_role in {ROLE_DB_ADMIN, ROLE_ADMIN}:
        return True
    return ArchiveAccessGrant.objects.filter(id_user=user, expires_at__gt=timezone.now()).exists()


# ---------------------------------------------------------------- регламентные задания

DEFAULT_JOBS = [
    ('release-reservations', 'Снятие просроченных резервов и отмена неоплаченных заказов', '*/5 * * * *', 'release_reservations'),
    ('backup-full', 'Полный бэкап БД (ночное окно)', '0 2 * * *', 'backup_full'),
    ('backup-incremental', 'Инкрементальный бэкап транзакционных данных', '0 */4 * * *', 'backup_incremental'),
    ('backup-schema', 'Бэкап схемы и справочников (также при каждом релизе)', '30 2 * * 1', 'backup_schema'),
    ('vacuum-analyze', 'VACUUM ANALYZE — обслуживание статистики и мёртвых строк', '30 3 * * *', 'vacuum_analyze'),
    ('cleanup-backups', 'Ротация копий: хранение 30 дней', '0 6 * * *', 'cleanup_backups'),
    ('verify-restore', 'Проверка restore на тестовом контуре', '0 5 1 * *', 'verify_restore'),
    ('archive-orders', 'Архивация закрытых заказов старше 365 дней', '0 4 1 * *', 'archive_orders'),
]


def ensure_default_jobs() -> None:
    for code, name, schedule, command in DEFAULT_JOBS:
        ScheduledJob.objects.get_or_create(
            job_code=code, defaults={'job_name': name, 'job_schedule': schedule, 'job_command': command})


def _cron_field_matches(expr: str, value: int, low: int, high: int) -> bool:
    for part in expr.split(','):
        step = 1
        if '/' in part:
            part, step_s = part.split('/')
            step = int(step_s)
        if part == '*':
            start, end = low, high
        elif '-' in part:
            start, end = map(int, part.split('-'))
        else:
            start = end = int(part)
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


def cron_matches(expr: str, moment: datetime) -> bool:
    minute, hour, dom, month, dow = expr.split()
    return (
        _cron_field_matches(minute, moment.minute, 0, 59)
        and _cron_field_matches(hour, moment.hour, 0, 23)
        and _cron_field_matches(dom, moment.day, 1, 31)
        and _cron_field_matches(month, moment.month, 1, 12)
        and _cron_field_matches(dow, (moment.weekday() + 1) % 7, 0, 6)
    )


def run_job(job: ScheduledJob, *, actor=None, request=None) -> ScheduledJob:
    from shop.services import orders as order_service

    handlers = {
        'release_reservations': lambda: (
            f'Снято резервов корзин: {order_service.release_expired_cart_reservations()}; '
            f'отменено неоплаченных заказов: {order_service.expire_unpaid_orders()}'),
        'backup_full': lambda: _backup_summary(create_backup('full', actor=actor)),
        'backup_incremental': lambda: _backup_summary(create_backup('incremental', actor=actor)),
        'backup_schema': lambda: _backup_summary(create_backup('schema', actor=actor)),
        'vacuum_analyze': vacuum_analyze,
        'cleanup_backups': lambda: f'Удалено копий: {cleanup_old_backups()}',
        'verify_restore': _verify_latest,
        'archive_orders': lambda: f'Заархивировано заказов: {archive_old_orders(actor=actor)}',
    }
    handler = handlers.get(job.job_command)
    try:
        if handler is None:
            raise ValidationError(f'Неизвестная команда {job.job_command}')
        output, status = handler(), 'success'
        if isinstance(output, str) and output.startswith('FAILED'):
            status = 'failed'
    except Exception as exc:  # задание не должно ронять планировщик
        output, status = f'{type(exc).__name__}: {exc}', 'failed'
    job.last_run_at, job.last_status, job.last_output = timezone.now(), status, str(output)[-4000:]
    job.save()
    write_audit(user=actor, object_type='db_job', object_id=job.pk, action='run',
                after={'status': status, 'output': str(output)[:500]}, request=request)
    return job


def _backup_summary(record: BackupRecord) -> str:
    prefix = '' if record.backup_status == 'success' else 'FAILED '
    return f'{prefix}{Path(record.file_path).name} ({record.file_size} байт)'


def _verify_latest() -> str:
    record = BackupRecord.objects.filter(backup_kind='full', backup_status='success').order_by('-created_at').first()
    if not record:
        return 'FAILED нет полной копии для проверки'
    record = verify_backup(record)
    return ('' if record.verify_status == 'ok' else 'FAILED ') + f'Проверка {Path(record.file_path).name}: {record.verify_status}'
