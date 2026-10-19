"""Нагрузочный тест: N параллельных оформлений заказа (по умолчанию 50) на ограниченный остаток.

Проверяет: время атомарной операции «корзина → резерв → платёж → заказ» (цель ≤ 2 с) и
отсутствие перепродажи — продано ровно столько, сколько было на складе. Требует PostgreSQL."""

import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections
from django.test.utils import override_settings

from shop.models import Order, Product, Stock
from shop.services import cart as cart_service
from shop.services import orders as order_service
from shop.services import pricing
from users.constants import ROLE_CUSTOMER
from users.models import AuthCredentials


class Command(BaseCommand):
    help = 'Параллельное оформление заказов: --orders 50 --stock 30'

    def add_arguments(self, parser):
        parser.add_argument('--orders', type=int, default=50)
        parser.add_argument('--stock', type=int, default=30, help='Остаток тестового товара (меньше числа заказов)')

    def handle(self, *args, **opts):
        if connection.vendor != 'postgresql':
            raise CommandError('Нагрузочный тест параллельных транзакций выполняется на PostgreSQL.')
        product, _ = Product.objects.get_or_create(product_sku='LOAD-TEST-1', defaults={'product_name': 'Товар нагрузочного теста'})
        pricing.set_price(product, Decimal('1000'), reason='load_test')
        Stock.objects.update_or_create(id_product=product, defaults={'stock_quantity': opts['stock'], 'stock_reserved': 0})
        users = []
        for i in range(opts['orders']):
            user, created = AuthCredentials.objects.get_or_create(email=f'load{i}@test.local', defaults={'user_role': ROLE_CUSTOMER})
            if created:
                user.set_password('Load12345')
                user.save()
            users.append(user)
        barrier = threading.Barrier(opts['orders'])
        results = []

        def worker(user):
            try:
                barrier.wait()
                started = time.perf_counter()
                try:
                    cart = cart_service.get_cart(user=user)
                    cart_service.clear(cart)
                    cart_service.add_item(cart, product, 1)
                    order, _ = order_service.checkout(cart, user=user, payment_method='card_online', offer_accepted=True,
                                                      delivery_address='Нагрузочный тест', contact_phone='+70000000000')
                    ok, info = True, order.order_number
                except ValidationError as exc:
                    ok, info = False, exc.messages[0]
                results.append((ok, (time.perf_counter() - started) * 1000, info))
            finally:
                connections.close_all()

        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            wall = time.perf_counter()
            with ThreadPoolExecutor(max_workers=opts['orders']) as pool:
                list(pool.map(worker, users))
            wall = (time.perf_counter() - wall) * 1000

        times = sorted(r[1] for r in results)
        ok = [r for r in results if r[0]]
        stock = Stock.objects.get(id_product=product)
        p95 = times[int(len(times) * 0.95) - 1]
        self.stdout.write(f'Параллельных оформлений: {len(results)}; успешно: {len(ok)}; отказов: {len(results) - len(ok)}')
        self.stdout.write(f'Время операции: медиана {statistics.median(times):.0f} мс, p95 {p95:.0f} мс, макс {times[-1]:.0f} мс; общее {wall:.0f} мс')
        self.stdout.write(f'Остаток: {stock.stock_quantity}, в резерве: {stock.stock_reserved}')
        oversold = stock.stock_reserved > stock.stock_quantity or len(ok) > opts['stock']
        self.stdout.write((self.style.ERROR if oversold else self.style.SUCCESS)(
            'ПЕРЕПРОДАЖА!' if oversold else 'Перепродажи нет: резерв не превышает остаток.'))
        status = 'OK' if p95 <= 2000 else 'SLOW'
        self.stdout.write(f'[{status}] Цель ≤ 2000 мс на операцию (p95)')
        refusals = {r[2] for r in results if not r[0]}
        if refusals:
            self.stdout.write('Причины отказов: ' + '; '.join(sorted(refusals)[:3]))
        # уборка: тестовые заказы отменяем, чтобы снять резерв
        for order in Order.objects.filter(id_user__email__startswith='load', order_status='NEW'):
            order_service.change_order_status(order, 'CANCELLED', actor=None, reason='load_test cleanup', system=True)
