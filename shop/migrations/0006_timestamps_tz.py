"""Исправление типов времени: TIMESTAMP → TIMESTAMPTZ.

Продаксовая БД разворачивалась из «Скрипт Бд.sql», где временные колонки
объявлены как TIMESTAMP (без часовой зоны). Django при USE_TZ=True пишет в
них UTC, а читает наивные datetime — сравнение с aware timezone.now()
падает (TypeError в промокодах, ValueError в localtime() на накладных,
RuntimeWarning при сохранении пользователей).

Миграция переконвертирует известные наивные колонки в timestamptz через
`AT TIME ZONE 'UTC'` (значения в них — именно UTC, сессия Postgres тоже
в UTC). DO-блок пропускает колонки, которые уже с зоной, — на тестовой БД
(создана миграциями Django) и повторном запуске это no-op.
"""

from django.db import migrations

# пары (таблица, колонка) — все наивные timestamp-колонки схемы
NAIVE_COLUMNS = [
    ('audit_log', 'created_at'),
    ('auth_credentials', 'created_at'),
    ('auth_credentials', 'updated_at'),
    ('carts', 'created_at'),
    ('carts', 'updated_at'),
    ('categories', 'created_at'),
    ('categories', 'updated_at'),
    ('orders', 'created_at'),
    ('orders', 'updated_at'),
    ('payments', 'created_at'),
    ('payments', 'updated_at'),
    ('prices', 'created_at'),
    ('prices', 'valid_from'),
    ('prices', 'valid_to'),
    ('products', 'created_at'),
    ('products', 'updated_at'),
    ('promotions', 'created_at'),
    ('promotions', 'start_at'),
    ('promotions', 'end_at'),
    ('promotions', 'updated_at'),
    ('returns', 'created_at'),
    ('returns', 'updated_at'),
    ('reviews', 'created_at'),
    ('reviews', 'updated_at'),
    ('stock', 'updated_at'),
    ('user_profiles', 'created_at'),
    ('user_profiles', 'updated_at'),
]

_values = ', '.join(f"('{t}', '{c}')" for t, c in NAIVE_COLUMNS)

UP = f"""
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.data_type = 'timestamp without time zone'
          AND (c.table_name, c.column_name) IN (VALUES {_values})
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE timestamptz USING %I AT TIME ZONE %L',
            r.table_name, r.column_name, r.column_name, 'UTC'
        );
    END LOOP;
END $$;
"""

# обратный ход: timestamptz → naive-UTC (симметрично исходному дефекту)
DOWN = f"""
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.data_type = 'timestamp with time zone'
          AND (c.table_name, c.column_name) IN (VALUES {_values})
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN %I TYPE timestamp USING %I AT TIME ZONE %L',
            r.table_name, r.column_name, r.column_name, 'UTC'
        );
    END LOOP;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0005_reference_data'),
    ]

    operations = [
        migrations.RunSQL(UP, DOWN),
    ]
