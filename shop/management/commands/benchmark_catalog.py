"""Замеры производительности каталога и поиска (цели ТЗ: список ≤ 300 мс, поиск ≤ 500 мс на 100k)."""

import statistics
import time

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection
from django.http import QueryDict

from shop.models import Category, Product
from shop.services import catalog


def measure(fn, runs):
    times = []
    for _ in range(runs):
        cache.clear()  # честный замер — без прогретого кеша фасетов
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times), max(times)


class Command(BaseCommand):
    help = 'Замер времени: каталог с фильтрами и пагинацией (50), полнотекстовый поиск'

    def add_arguments(self, parser):
        parser.add_argument('--runs', type=int, default=7)

    def handle(self, *args, **opts):
        total = Product.objects.count()
        cat = Category.objects.filter(category_level=1).first()
        scenarios = {
            'Каталог, 1-я страница (популярные)': 'sort=popular',
            'Каталог: категория + цена + бренд + в наличии': f'category={cat.category_slug if cat else ""}&price_min=500&price_max=20000&in_stock=1&sort=price_asc',
            'Каталог: характеристики (цвет, подключение)': 'f_color=Чёрный&f_connection=USB&sort=new',
            'Каталог: 100-я страница': 'sort=rating&page=100',
            'Поиск: «беспроводная клавиатура»': 'q=беспроводная клавиатура',
            'Поиск по артикулу': 'q=GEN-0050000',
        }
        self.stdout.write(f'СУБД: {connection.vendor}; товаров: {total}; прогонов: {opts["runs"]}\n')
        for title, query in scenarios.items():
            params = QueryDict(query)
            page = int(params.get('page', 1))

            def run():
                qs, _, _ = catalog.search(catalog.parse_filters(params))
                list(qs[(page - 1) * 50: page * 50])
                qs.count()
            median, worst = measure(run, opts['runs'])
            limit = 500 if 'Поиск' in title else 300
            mark = 'OK ' if median <= limit else 'SLOW'
            self.stdout.write(f'[{mark}] {title}: медиана {median:.0f} мс, макс {worst:.0f} мс (цель ≤ {limit} мс)')
