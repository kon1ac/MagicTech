"""Синхронизация PostgreSQL-последовательностей с реальными max(id) в таблицах.

Нужна, когда данные вставляются напрямую через SQL (pgAdmin/psql),
а не через Django ORM — последовательности не обновляются автоматически.

Запуск: python manage.py sync_sequences
"""

from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Синхронизирует последовательности PostgreSQL с реальными max(id) в таблицах'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Только показать, что будет изменено, не применяя',
        )

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Находим все таблицы с SERIAL/IDENTITY колонкой
            cursor.execute("""
                SELECT c.table_name, c.column_name,
                       pg_get_serial_sequence(quote_ident(c.table_name), c.column_name) AS seq
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON t.table_name = c.table_name AND t.table_schema = c.table_schema
                WHERE c.table_schema = 'public'
                  AND t.table_type = 'BASE TABLE'
                  AND (c.column_default LIKE 'nextval%' OR c.is_identity = 'YES')
            """)
            tables = cursor.fetchall()

        total_synced = 0
        for table_name, column_name, seq in tables:
            if not seq:
                continue

            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT COALESCE(MAX({column_name}), 0) FROM "{table_name}"'
                )
                max_val = cursor.fetchone()[0]

            if max_val <= 0:
                # Таблица пуста — ставим seq=1
                with connection.cursor() as cursor:
                    cursor.execute(f'SELECT setval(%s, 1, false)', [seq])
                if options['dry_run']:
                    self.stdout.write(f'  [EMPTY] {table_name}.{column_name} → seq=1')
                else:
                    self.stdout.write(f'  [EMPTY] {table_name}.{column_name} → 1')
                total_synced += 1
            else:
                if options['dry_run']:
                    self.stdout.write(
                        f'  [DRY] {table_name}.{column_name}: max={max_val}, seq сейчас? → setval({seq}, {max_val}, true)'
                    )
                else:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f'SELECT setval(%s, %s, true)', [seq, max_val]
                        )
                    self.stdout.write(
                        f'  [OK] {table_name}.{column_name}: max={max_val}, seq → {max_val}'
                    )
                    total_synced += 1

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(f'\nDRY RUN: {total_synced} последовательностей потребуют обновления')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'\nГотово: синхронизировано {total_synced} последовательностей')
            )
