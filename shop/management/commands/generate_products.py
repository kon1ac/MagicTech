"""Генерация N синтетических товаров (для замеров производительности каталога на 100k)."""

import random
import time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from shop.models import Brand, Category, Price, Product, Stock
from shop.services.catalog import invalidate_catalog_cache

WORDS = ['Клавиатура', 'Мышь', 'Гарнитура', 'Коврик', 'Кабель', 'Хаб', 'Веб-камера', 'Подставка', 'Кресло', 'Кулер']
ADJ = ['беспроводная', 'игровая', 'офисная', 'компактная', 'механическая', 'тихая', 'эргономичная', 'профессиональная']


class Command(BaseCommand):
    help = 'Создаёт N синтетических товаров с ценами и остатками: --count 100000'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100_000)
        parser.add_argument('--prefix', default='GEN')

    def handle(self, *args, **opts):
        rnd = random.Random(42)
        categories = list(Category.objects.filter(category_level__gte=2).values_list('pk', flat=True)) or \
            list(Category.objects.values_list('pk', flat=True))
        brands = list(Brand.objects.values_list('pk', flat=True))
        if not categories or not brands:
            self.stderr.write('Сначала выполните seed_magtech')
            return
        started = time.monotonic()
        batch = 5000
        start = Product.objects.filter(product_sku__startswith=opts['prefix']).count()
        for offset in range(start, start + opts['count'], batch):
            with transaction.atomic():
                products = [Product(
                    product_sku=f'{opts["prefix"]}-{i:07d}',
                    product_name=f'{rnd.choice(WORDS)} {rnd.choice(ADJ)} модель {i}',
                    product_description=f'Синтетический товар №{i} для нагрузочного тестирования каталога.',
                    id_category_id=rnd.choice(categories), id_brand_id=rnd.choice(brands),
                    product_characteristics={'color': rnd.choice(['Чёрный', 'Белый', 'Серый', 'Красный']),
                                             'connection': rnd.choice(['USB', 'Bluetooth', '2.4 ГГц', 'USB-C']),
                                             'backlight': rnd.choice(['RGB', 'Нет', 'Белая'])},
                    sales_count=rnd.randint(0, 500), rating_avg=Decimal(rnd.randint(0, 50)) / 10,
                    cost_price=Decimal(rnd.randint(100, 9000)),
                ) for i in range(offset, min(offset + batch, start + opts['count']))]
                Product.objects.bulk_create(products, batch_size=batch)
                Price.objects.bulk_create([Price(id_product=p, product_price=Decimal(rnd.randint(190, 49990)),
                                                 price_reason='generate_products') for p in products], batch_size=batch)
                Stock.objects.bulk_create([Stock(id_product=p, stock_quantity=rnd.randint(0, 100), stock_reserved=0)
                                           for p in products], batch_size=batch)
            self.stdout.write(f'  {min(offset + batch, start + opts["count"]) - start} / {opts["count"]}')
        invalidate_catalog_cache()
        self.stdout.write(self.style.SUCCESS(f'Создано {opts["count"]} товаров за {time.monotonic() - started:.1f} с. '
                                             'Выполните VACUUM ANALYZE (регламентное задание vacuum-analyze).'))
