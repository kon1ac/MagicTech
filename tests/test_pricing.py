from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from shop.services import pricing
from tests.base import MagicTestCase


class PricingTests(MagicTestCase):
    def lines(self, *items):
        return [pricing.Line(product=p, quantity=q, price=pricing.get_current_price(p)) for p, q in items]

    def test_no_promotions(self):
        totals = pricing.calculate(self.lines((self.mouse, 2), (self.keyboard, 1)))
        self.assertEqual(totals.subtotal, Decimal('9000'))
        self.assertEqual(totals.discount, 0)
        self.assertEqual(totals.total, Decimal('9000'))

    def test_percent_promotion_by_parent_category(self):
        self.promo(promotion_value=Decimal('10'), categories=[self.root])
        totals = pricing.calculate(self.lines((self.mouse, 1)))
        self.assertEqual(totals.discount, Decimal('200.00'))

    def test_promotion_only_for_its_category(self):
        self.promo(promotion_value=Decimal('10'), categories=[self.mice])
        totals = pricing.calculate(self.lines((self.mouse, 1), (self.keyboard, 1)))
        self.assertEqual(totals.discount, Decimal('200.00'))

    def test_expired_promotion_ignored(self):
        self.promo(start_at=timezone.now() - timedelta(days=10), end_at=timezone.now() - timedelta(days=1))
        self.assertEqual(pricing.calculate(self.lines((self.mouse, 1))).discount, 0)

    def test_best_automatic_promotion_wins(self):
        self.promo(promotion_value=Decimal('5'))
        self.promo(promotion_value=Decimal('15'))
        self.assertEqual(pricing.calculate(self.lines((self.mouse, 1))).discount, Decimal('300.00'))

    def test_fixed_promo_code_distributed_and_capped(self):
        self.promo(promotion_type='fixed', promotion_value=Decimal('700'), promotion_promo_code='FIX700')
        totals = pricing.calculate(self.lines((self.mouse, 1), (self.keyboard, 1)), 'FIX700')
        self.assertEqual(totals.discount, Decimal('700.00'))
        self.assertEqual(sum(l.discount for l in totals.lines), Decimal('700.00'))
        self.assertEqual(totals.total, Decimal('6300.00'))

    def test_fixed_discount_never_exceeds_total(self):
        self.promo(promotion_type='fixed', promotion_value=Decimal('99999'), promotion_promo_code='HUGE')
        totals = pricing.calculate(self.lines((self.mouse, 1)), 'HUGE')
        self.assertEqual(totals.total, Decimal('0'))

    def test_promo_code_validations(self):
        now = timezone.now()
        self.promo(promotion_promo_code='OLD', end_at=now - timedelta(hours=1), start_at=now - timedelta(days=2))
        self.promo(promotion_promo_code='LIMIT', usage_limit=1, usage_count=1)
        self.promo(promotion_promo_code='MIN', promotion_min_sum=Decimal('10000'))
        self.promo(promotion_promo_code='QTY', promotion_min_qty=3)
        lines = self.lines((self.mouse, 1))
        self.assertIn('истёк', pricing.validate_promo_code('OLD', lines)[1])
        self.assertIn('Лимит', pricing.validate_promo_code('LIMIT', lines)[1])
        self.assertIn('Минимальная сумма', pricing.validate_promo_code('MIN', lines)[1])
        self.assertIn('количество', pricing.validate_promo_code('QTY', lines)[1])
        self.assertIn('не найден', pricing.validate_promo_code('NOPE', lines)[1])

    def test_non_stackable_code_takes_max(self):
        self.promo(promotion_value=Decimal('10'))
        self.promo(promotion_value=Decimal('20'), promotion_promo_code='TWENTY')
        totals = pricing.calculate(self.lines((self.mouse, 1)), 'TWENTY')
        self.assertEqual(totals.discount, Decimal('400.00'))

    def test_stackable_code_adds_up(self):
        self.promo(promotion_value=Decimal('10'))
        self.promo(promotion_value=Decimal('20'), promotion_promo_code='STACK', is_stackable=True)
        totals = pricing.calculate(self.lines((self.mouse, 1)), 'STACK')
        self.assertEqual(totals.discount, Decimal('600.00'))

    def test_negative_price_rejected(self):
        with self.assertRaises(ValidationError):
            pricing.set_price(self.mouse, Decimal('-1'))

    def test_price_versioning_keeps_one_current(self):
        pricing.set_price(self.mouse, Decimal('2500'), reason='Повышение')
        self.assertEqual(self.mouse.prices.filter(valid_to__isnull=True).count(), 1)
        self.assertEqual(self.mouse.prices.count(), 2)
        self.assertEqual(self.mouse.current_price, Decimal('2500'))

    def test_order_keeps_price_snapshot(self):
        order, _ = self.place_order()
        pricing.set_price(self.mouse, Decimal('9999'))
        item = order.items.get()
        self.assertEqual(item.order_item_price, Decimal('2000'))
