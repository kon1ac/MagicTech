"""PostgreSQL: полнотекстовый поиск с морфологией (словарь russian).

Генерируемая колонка search_vector + GIN-индекс; индекс jsonb по характеристикам
для динамических фильтров. На других СУБД миграция ничего не делает."""

from django.db import migrations

FORWARD = [
    """ALTER TABLE products ADD COLUMN IF NOT EXISTS search_vector tsvector
       GENERATED ALWAYS AS (
           setweight(to_tsvector('russian', coalesce(product_name, '')), 'A') ||
           setweight(to_tsvector('simple', coalesce(product_sku, '')), 'A') ||
           setweight(to_tsvector('russian', coalesce(product_description, '')), 'C')
       ) STORED""",
    'CREATE INDEX IF NOT EXISTS products_search_gin ON products USING GIN (search_vector)',
    'CREATE INDEX IF NOT EXISTS products_chars_gin ON products USING GIN ((product_characteristics::jsonb) jsonb_path_ops)',
    'CREATE INDEX IF NOT EXISTS stock_product_idx ON stock (id_product) INCLUDE (stock_quantity, stock_reserved)',
]
BACKWARD = [
    'DROP INDEX IF EXISTS stock_product_idx',
    'DROP INDEX IF EXISTS products_chars_gin',
    'DROP INDEX IF EXISTS products_search_gin',
    'ALTER TABLE products DROP COLUMN IF EXISTS search_vector',
]


def run(statements):
    def apply(apps, schema_editor):
        if schema_editor.connection.vendor != 'postgresql':
            return
        for sql in statements:
            schema_editor.execute(sql)

    return apply


class Migration(migrations.Migration):
    dependencies = [('shop', '0003_archiveaccessgrant_archivedorder_backuprecord_and_more')]

    operations = [migrations.RunPython(run(FORWARD), run(BACKWARD))]
