from decimal import Decimal

from django.core.exceptions import ValidationError

from shop.models import Order, ReturnReason
from shop.services import orders as order_service
from shop.services import returns as return_service
from shop.services import reviews as review_service
from shop.services.stock import write_off_for_order
from tests.base import MagicTestCase


class CompletedOrderMixin:
    def completed_order(self, user=None, items=None):
        order, payment = self.place_order(user=user, items=items or [(self.mouse, 2)])
        self.pay(payment)
        for status in ('CONFIRMED', 'ASSEMBLY'):
            order_service.change_order_status(order, status, actor=self.admin)
        order.refresh_from_db()
        write_off_for_order(order, actor=self.picker)
        order_service.change_order_status(order, 'PACKED', actor=self.picker, system=True)
        order_service.change_order_status(order, 'COMPLETED', actor=self.admin)
        return Order.objects.get(pk=order.pk)


class ReturnTests(CompletedOrderMixin, MagicTestCase):
    def setUp(self):
        super().setUp()
        self.reason = ReturnReason.objects.get(reason_code='not_fit')
        self.defect = ReturnReason.objects.get(reason_code='defect')

    def test_return_only_for_completed_order(self):
        order, _ = self.place_order()
        with self.assertRaisesMessage(ValidationError, 'завершённому'):
            return_service.create_return(order, user=self.buyer, reason=self.reason, description='',
                                         quantities={order.items.get().pk: 1})

    def test_cannot_return_more_than_bought(self):
        order = self.completed_order()
        item = order.items.get()
        return_service.create_return(order, user=self.buyer, reason=self.reason, description='', quantities={item.pk: 1})
        with self.assertRaises(ValidationError):
            return_service.create_return(order, user=self.buyer, reason=self.reason, description='', quantities={item.pk: 2})

    def test_full_flow_restock_and_refund(self):
        order = self.completed_order()
        ret = return_service.create_return(order, user=self.buyer, reason=self.reason, description='Не подошла',
                                           quantities={order.items.get().pk: 2})
        self.assertEqual(ret.refund_amount, Decimal('4000.00'))
        qty_before = self.stock(self.mouse).stock_quantity
        for status in ('IN_REVIEW', 'APPROVED', 'RETURNED_TO_WAREHOUSE', 'REFUNDED'):
            ret = return_service.change_return_status(ret, status, actor=self.admin, decision='Ок')
        self.assertEqual(self.stock(self.mouse).stock_quantity, qty_before + 2)
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'RETURNED')
        self.assertEqual(order.payments.get().payment_status, 'REFUNDED')
        self.assertTrue(ret.is_locked)

    def test_defective_goods_not_restocked(self):
        order = self.completed_order()
        ret = return_service.create_return(order, user=self.buyer, reason=self.defect, description='Не работает',
                                           quantities={order.items.get().pk: 1})
        qty_before = self.stock(self.mouse).stock_quantity
        for status in ('IN_REVIEW', 'APPROVED', 'RETURNED_TO_WAREHOUSE'):
            ret = return_service.change_return_status(ret, status, actor=self.admin, decision='Брак подтверждён')
        self.assertEqual(self.stock(self.mouse).stock_quantity, qty_before)

    def test_cannot_skip_review(self):
        order = self.completed_order()
        ret = return_service.create_return(order, user=self.buyer, reason=self.reason, description='',
                                           quantities={order.items.get().pk: 1})
        with self.assertRaises(ValidationError):
            return_service.change_return_status(ret, 'REFUNDED', actor=self.admin)

    def test_locked_return_requires_audit_reason_and_bumps_version(self):
        order = self.completed_order()
        ret = return_service.create_return(order, user=self.buyer, reason=self.reason, description='',
                                           quantities={order.items.get().pk: 1})
        for status in ('IN_REVIEW', 'APPROVED'):
            ret = return_service.change_return_status(ret, status, actor=self.admin, decision='Ок')
        with self.assertRaises(ValidationError):
            return_service.edit_return(ret, actor=self.admin, reason='', changes={'refund_amount': Decimal('100')})
        ret = return_service.edit_return(ret, actor=self.admin, reason='Ошибка в сумме',
                                         changes={'refund_amount': Decimal('1900')})
        self.assertEqual(ret.version, 2)
        from shop.models import AuditLog
        self.assertTrue(AuditLog.objects.filter(audit_object_type='return', audit_action='audit_edit',
                                                audit_reason='Ошибка в сумме').exists())


class ReviewTests(CompletedOrderMixin, MagicTestCase):
    def test_only_buyers_can_review(self):
        with self.assertRaisesMessage(ValidationError, 'покупатель'):
            review_service.create_review(self.buyer, self.mouse, rating=5, text='Отлично')
        self.completed_order()
        review = review_service.create_review(self.buyer, self.mouse, rating=5, text='Отлично')
        self.assertEqual(review.review_status, 'pending')

    def test_one_review_per_product(self):
        self.completed_order()
        review_service.create_review(self.buyer, self.mouse, rating=5, text='Отлично')
        with self.assertRaises(ValidationError):
            review_service.create_review(self.buyer, self.mouse, rating=4, text='Ещё раз')

    def test_questions_do_not_require_purchase(self):
        q = review_service.create_review(self.other_buyer, self.mouse, rating=None, text='Есть подсветка?', is_question=True)
        self.assertEqual(q.review_type, 'question')

    def test_rating_recalculated_on_moderation_and_delete(self):
        self.completed_order(user=self.buyer)
        self.completed_order(user=self.other_buyer)
        r1 = review_service.create_review(self.buyer, self.mouse, rating=5, text='A')
        r2 = review_service.create_review(self.other_buyer, self.mouse, rating=2, text='B')
        review_service.moderate(r1, 'approved', actor=self.merch)
        self.mouse.refresh_from_db()
        self.assertEqual((self.mouse.rating_avg, self.mouse.rating_count), (Decimal('5.00'), 1))
        review_service.moderate(r2, 'approved', actor=self.merch)
        self.mouse.refresh_from_db()
        self.assertEqual(self.mouse.rating_avg, Decimal('3.50'))
        review_service.delete_review(r2, actor=self.admin)
        self.mouse.refresh_from_db()
        self.assertEqual((self.mouse.rating_avg, self.mouse.rating_count), (Decimal('5.00'), 1))
