from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from shop.models import Order, Payment, Reservation
from shop.services import orders as order_service
from shop.services import payments as payment_service
from shop.services.reports import net_revenue
from tests.base import MagicTestCase


class CheckoutTests(MagicTestCase):
    def test_checkout_creates_order_reserve_and_payment(self):
        order, payment = self.place_order(items=[(self.mouse, 2)])
        self.assertRegex(order.order_number, r'^MT-\d{6}-\d{6}$')
        self.assertEqual(order.total, Decimal('4000'))
        self.assertEqual(payment.payment_status, 'PENDING')
        self.assertEqual(payment.logs.count(), 2)
        res = Reservation.objects.get(id_order=order)
        self.assertEqual(res.reservation_quantity, 2)
        self.assertIsNotNone(res.expires_at)
        self.assertEqual(self.stock(self.mouse).stock_reserved, 2)

    def test_checkout_requires_offer(self):
        cart = self.cart_with(self.buyer, (self.mouse, 1))
        with self.assertRaisesMessage(ValidationError, 'оферты'):
            order_service.checkout(cart, user=self.buyer, payment_method='card_online', offer_accepted=False)

    def test_min_order_total(self):
        cheap = self.make_product('CB-1', 'Кабель', self.root, Decimal('100'), 10)
        with self.assertRaisesMessage(ValidationError, 'Минимальная сумма'):
            self.place_order(items=[(cheap, 1)])
        self.assertFalse(Order.objects.exists())

    def test_checkout_rolls_back_completely_on_error(self):
        cart = self.cart_with(self.buyer, (self.mouse, 1), (self.keyboard, 1))
        self.keyboard.is_active = False
        self.keyboard.save()
        with self.assertRaises(ValidationError):
            order_service.checkout(cart, user=self.buyer, payment_method='card_online', offer_accepted=True)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())
        cart.refresh_from_db()
        self.assertEqual(cart.cart_status, 'active')
        self.assertEqual(self.stock(self.mouse).stock_reserved, 1)  # резерв корзины не потерян

    def test_promo_code_usage_counted(self):
        promo = self.promo(promotion_promo_code='CODE', usage_limit=5)
        order, _ = self.place_order(promo='CODE')
        promo.refresh_from_db()
        self.assertEqual(promo.usage_count, 1)
        self.assertEqual(order.discount_total, Decimal('200.00'))
        self.assertEqual(order.order_promotions.count(), 1)


class StatusFlowTests(MagicTestCase):
    def test_cannot_skip_stages(self):
        order, _ = self.place_order(method='cash_on_delivery')
        with self.assertRaisesMessage(ValidationError, 'по регламенту'):
            order_service.change_order_status(order, 'PACKED', actor=self.admin)

    def test_online_order_needs_payment_before_confirmation(self):
        order, _ = self.place_order()
        with self.assertRaises(ValidationError):
            order_service.change_order_status(order, 'CONFIRMED', actor=self.admin)
        with self.assertRaises(ValidationError):
            order_service.change_order_status(order, 'PAID', actor=self.admin)

    def test_cannot_complete_unpaid_cod_order(self):
        order, _ = self.place_order(method='cash_on_delivery')
        for status in ('CONFIRMED', 'ASSEMBLY'):
            order_service.change_order_status(order, status, actor=self.admin)
        order_service.change_order_status(order, 'PACKED', actor=self.picker, system=True)
        with self.assertRaises(ValidationError):
            order_service.change_order_status(order, 'COMPLETED', actor=self.admin)
        payment_service.mark_cash_on_delivery_paid(order, actor=self.admin)
        order_service.change_order_status(order, 'COMPLETED', actor=self.admin)
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'COMPLETED')

    def test_cancel_requires_reason(self):
        order, _ = self.place_order(method='cash_on_delivery')
        with self.assertRaisesMessage(ValidationError, 'причину'):
            order_service.change_order_status(order, 'CANCELLED', actor=self.admin)


class PaymentTests(MagicTestCase):
    def test_webhook_success_marks_order_paid(self):
        order, payment = self.place_order()
        self.pay(payment)
        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.order_status, 'PAID')
        self.assertEqual(payment.payment_status, 'SUCCESS')
        self.assertGreater(payment.payment_commission, 0)
        self.assertIsNone(order.reservations.get().expires_at)

    def test_webhook_is_idempotent(self):
        order, payment = self.place_order()
        self.pay(payment)
        self.pay(payment)
        self.assertEqual(Order.objects.get(pk=order.pk).order_status, 'PAID')
        self.assertEqual(payment.logs.filter(log_direction='callback').count(), 2)

    def test_webhook_bad_signature(self):
        _, payment = self.place_order()
        body = payment_service.build_webhook(payment, 'payment.succeeded')
        with self.assertRaises(PermissionError):
            payment_service.process_webhook(body, 'forged')

    def test_webhook_amount_mismatch(self):
        _, payment = self.place_order()
        body = payment_service.build_webhook(payment, 'payment.succeeded').replace(b'2000.00', b'1.00')
        with self.assertRaises(ValidationError):
            payment_service.process_webhook(body, payment_service.sign(body))

    def test_payment_failure_cancels_and_releases(self):
        order, payment = self.place_order()
        body = payment_service.build_webhook(payment, 'payment.canceled')
        payment_service.process_webhook(body, payment_service.sign(body))
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'CANCELLED')
        self.assertEqual(self.stock(self.mouse).stock_reserved, 0)

    def test_unpaid_orders_expire(self):
        order, _ = self.place_order()
        Order.objects.filter(pk=order.pk).update(payment_due_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(order_service.expire_unpaid_orders(), 1)
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'CANCELLED')
        self.assertEqual(self.stock(self.mouse).stock_reserved, 0)

    def test_manual_confirmation(self):
        order, payment = self.place_order()
        payment_service.confirm_manually(payment, actor=self.accountant, reason='Реестр №5')
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'PAID')

    def test_partial_and_full_refund(self):
        _, payment = self.place_order()
        self.pay(payment)
        payment = payment_service.refund(Payment.objects.get(pk=payment.pk), Decimal('500'), actor=self.accountant, reason='Частично')
        self.assertEqual(payment.payment_status, 'PARTIALLY_REFUNDED')
        with self.assertRaises(ValidationError):
            payment_service.refund(payment, Decimal('1501'), actor=self.accountant, reason='Слишком много')
        payment = payment_service.refund(payment, Decimal('1500'), actor=self.accountant, reason='Остаток')
        self.assertEqual(payment.payment_status, 'REFUNDED')

    def test_payment_log_payload_is_sanitized(self):
        """payload веб-хука приходит извне: Decimal не должен ронять запись,
        а гигантское тело — раздувать payment_logs."""
        _, payment = self.place_order()
        payment_service.log(payment, 'callback', {'amount': Decimal('10.50'), 'obj': payment})
        self.assertEqual(payment.logs.get(log_direction='callback').log_payload['amount'], '10.50')

        payment_service.log(payment, 'callback', {'blob': 'x' * 200_000})
        huge = payment.logs.get(log_direction='callback', log_payload__truncated=True).log_payload
        self.assertTrue(huge['truncated'])
        self.assertLess(len(str(huge)), 20_000)

    def test_net_revenue_subtracts_refunds(self):
        """Выручка дашборда — факт поступлений: возвраты вычитаются, полностью
        возвращённый платёж даёт ноль (раньше считалось «грязными» и было завышено)."""
        self.assertEqual(net_revenue(), Decimal('0'))
        _, payment = self.place_order()
        self.pay(payment)
        self.assertEqual(net_revenue(), Decimal('2000'))
        payment = payment_service.refund(Payment.objects.get(pk=payment.pk), Decimal('500'),
                                         actor=self.accountant, reason='Частично')
        self.assertEqual(net_revenue(), Decimal('1500'))
        payment = payment_service.refund(payment, Decimal('1500'), actor=self.accountant, reason='Остаток')
        self.assertEqual(net_revenue(), Decimal('0'))
        # отменённый неоплаченный заказ в выручку не попадает
        order, _ = self.place_order()
        order_service.change_order_status(order, 'CANCELLED', actor=self.admin, reason='Передумал')
        self.assertEqual(net_revenue(), Decimal('0'))
