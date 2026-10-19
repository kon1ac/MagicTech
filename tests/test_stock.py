from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from shop.models import Reservation, StockMovement
from shop.services import cart as cart_service
from shop.services import orders as order_service
from shop.services.stock import adjust_stock, receive_stock, write_off_for_order
from tests.base import MagicTestCase


class StockTests(MagicTestCase):
    def test_add_to_cart_reserves_stock(self):
        self.cart_with(self.buyer, (self.mouse, 3))
        stock = self.stock(self.mouse)
        self.assertEqual((stock.stock_quantity, stock.stock_reserved), (10, 3))
        res = Reservation.objects.get(id_product=self.mouse, reservation_status='active')
        self.assertGreater(res.expires_at, timezone.now() + timedelta(minutes=14))

    def test_cannot_reserve_more_than_available(self):
        self.cart_with(self.other_buyer, (self.keyboard, 4))
        with self.assertRaisesMessage(ValidationError, 'доступно 1'):
            self.cart_with(self.buyer, (self.keyboard, 2))

    def test_change_and_remove_cart_quantity(self):
        cart = self.cart_with(self.buyer, (self.mouse, 2))
        cart_service.set_quantity(cart, self.mouse, 5)
        self.assertEqual(self.stock(self.mouse).stock_reserved, 5)
        cart_service.set_quantity(cart, self.mouse, 0)
        self.assertEqual(self.stock(self.mouse).stock_reserved, 0)
        self.assertFalse(cart.items.exists())

    def test_expired_cart_reservation_released_by_cron(self):
        self.cart_with(self.buyer, (self.mouse, 2))
        Reservation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(order_service.release_expired_cart_reservations(), 1)
        self.assertEqual(self.stock(self.mouse).stock_reserved, 0)
        self.assertEqual(Reservation.objects.get().reservation_status, 'expired')

    def test_adjust_cannot_go_negative_or_below_reserve(self):
        with self.assertRaises(ValidationError):
            adjust_stock(self.mouse, -11, actor=self.admin, reason='Недостача')
        self.cart_with(self.buyer, (self.mouse, 4))
        with self.assertRaisesMessage(ValidationError, 'зарезервированного'):
            adjust_stock(self.mouse, -7, actor=self.admin, reason='Недостача')
        self.assertEqual(self.stock(self.mouse).stock_quantity, 10)

    def test_adjust_requires_reason(self):
        with self.assertRaises(ValidationError):
            adjust_stock(self.mouse, 1, actor=self.admin, reason=' ')

    def test_receipt_with_discrepancy_is_recorded(self):
        movement = receive_stock(self.mouse, 8, actor=self.picker, document_number='ПН-1', expected_quantity=10)
        self.assertEqual(self.stock(self.mouse).stock_quantity, 18)
        self.assertIn('Расхождение', movement.movement_reason)
        self.assertEqual(movement.expected_quantity, 10)

    def test_write_off_consumes_reservation(self):
        order, _ = self.place_order(items=[(self.mouse, 2)], method='cash_on_delivery')
        write_off_for_order(order, actor=self.picker)
        stock = self.stock(self.mouse)
        self.assertEqual((stock.stock_quantity, stock.stock_reserved), (8, 0))
        self.assertTrue(StockMovement.objects.filter(movement_type='write_off', id_order=order).exists())

    def test_write_off_is_atomic(self):
        order, _ = self.place_order(items=[(self.mouse, 1), (self.keyboard, 1)], method='cash_on_delivery')
        # кто-то «увёл» клавиатуры мимо системы — списание всего заказа должно откатиться
        from shop.models import Stock
        Stock.objects.filter(id_product=self.keyboard).update(stock_quantity=0, stock_reserved=0)
        order.reservations.filter(id_product=self.keyboard).update(reservation_status='released')
        with self.assertRaises(ValidationError):
            write_off_for_order(order, actor=self.picker)
        self.assertEqual(self.stock(self.mouse).stock_quantity, 10)

    def test_cancel_before_packing_releases_reserve(self):
        order, _ = self.place_order(items=[(self.mouse, 3)], method='cash_on_delivery')
        order_service.change_order_status(order, 'CANCELLED', actor=self.admin, reason='Клиент передумал')
        stock = self.stock(self.mouse)
        self.assertEqual((stock.stock_quantity, stock.stock_reserved), (10, 0))

    def test_cancel_after_packing_returns_goods(self):
        order, _ = self.place_order(items=[(self.mouse, 3)], method='cash_on_delivery')
        for status in ('CONFIRMED', 'ASSEMBLY'):
            order_service.change_order_status(order, status, actor=self.admin)
        write_off_for_order(order, actor=self.picker)
        order_service.change_order_status(order, 'PACKED', actor=self.picker, system=True)
        self.assertEqual(self.stock(self.mouse).stock_quantity, 7)
        order_service.change_order_status(order, 'CANCELLED', actor=self.admin, reason='Отказ')
        self.assertEqual(self.stock(self.mouse).stock_quantity, 10)
        self.assertTrue(StockMovement.objects.filter(movement_type='cancel_restore').exists())
