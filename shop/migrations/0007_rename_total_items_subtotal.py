"""Переименование orders.total_items → orders.subtotal.

Поле всегда содержало сумму товаров до скидки (pricing.calculate → totals.subtotal),
а не количество штук: имя вводило в заблуждение. На PostgreSQL RENAME COLUMN
меняет только метаданные — данные и индексы остаются на месте.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0006_timestamps_tz'),
    ]

    operations = [
        migrations.RenameField(
            model_name='order',
            old_name='total_items',
            new_name='subtotal',
        ),
    ]
