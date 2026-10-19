"""Справочники: единицы измерения, статусы заказов, причины возврата, типы акций,
регламентные задания СУБД."""

from django.db import migrations

UNITS = [('pcs', 'шт.'), ('set', 'компл.'), ('m', 'м'), ('g', 'г'), ('pack', 'уп.')]
STATUSES = [
    ('NEW', 'Новый', 1, False), ('PAID', 'Оплачен', 2, False), ('CONFIRMED', 'Подтверждён', 3, False),
    ('ASSEMBLY', 'В сборке', 4, False), ('PACKED', 'Собран и упакован', 5, False),
    ('COMPLETED', 'Завершён', 6, True), ('CANCELLED', 'Отменён', 7, True), ('RETURNED', 'Возврат', 8, True),
]
REASONS = [
    ('defect', 'Брак / не работает', True), ('not_fit', 'Не подошёл', False),
    ('wrong_item', 'Привезли не тот товар', False), ('damaged', 'Повреждён при доставке', True),
    ('changed_mind', 'Передумал', False),
]
PROMO_TYPES = [('percent', 'Процент'), ('fixed', 'Фиксированная сумма')]
JOBS = [
    ('release-reservations', 'Снятие просроченных резервов и отмена неоплаченных заказов', '*/5 * * * *', 'release_reservations'),
    ('backup-full', 'Полный бэкап БД (ночное окно)', '0 2 * * *', 'backup_full'),
    ('backup-incremental', 'Инкрементальный бэкап транзакционных данных', '0 */4 * * *', 'backup_incremental'),
    ('backup-schema', 'Бэкап схемы и справочников (также при каждом релизе)', '30 2 * * 1', 'backup_schema'),
    ('vacuum-analyze', 'VACUUM ANALYZE — обслуживание статистики и мёртвых строк', '30 3 * * *', 'vacuum_analyze'),
    ('cleanup-backups', 'Ротация копий: хранение 30 дней', '0 6 * * *', 'cleanup_backups'),
    ('verify-restore', 'Проверка restore на тестовом контуре', '0 5 1 * *', 'verify_restore'),
    ('archive-orders', 'Архивация закрытых заказов старше 365 дней', '0 4 1 * *', 'archive_orders'),
]


def forward(apps, schema_editor):
    Unit = apps.get_model('shop', 'Unit')
    for code, name in UNITS:
        Unit.objects.get_or_create(unit_code=code, defaults={'unit_name': name})
    OrderStatusRef = apps.get_model('shop', 'OrderStatusRef')
    for code, label, order, final in STATUSES:
        OrderStatusRef.objects.update_or_create(
            status_code=code, defaults={'status_label': label, 'sort_order': order, 'is_final': final})
    ReturnReason = apps.get_model('shop', 'ReturnReason')
    for code, name, defect in REASONS:
        ReturnReason.objects.get_or_create(reason_code=code, defaults={'reason_name': name, 'is_defect': defect})
    PromotionTypeRef = apps.get_model('shop', 'PromotionTypeRef')
    for code, name in PROMO_TYPES:
        PromotionTypeRef.objects.get_or_create(type_code=code, defaults={'type_name': name})
    ScheduledJob = apps.get_model('shop', 'ScheduledJob')
    for code, name, schedule, command in JOBS:
        ScheduledJob.objects.get_or_create(
            job_code=code, defaults={'job_name': name, 'job_schedule': schedule, 'job_command': command})


class Migration(migrations.Migration):
    dependencies = [('shop', '0004_postgres_fulltext')]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
