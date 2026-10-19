"""Цены, акции и промокоды, расчёт корзины.

Правила комбинирования скидок:
* к позиции применяется одна автоматическая акция — с максимальной скидкой;
* промокод суммируется с автоматической акцией, только если у него стоит is_stackable;
  иначе для каждой позиции берётся большая из двух скидок;
* «fixed»-скидка — на заказ, распределяется по подходящим позициям пропорционально сумме;
* скидка не превышает стоимость позиции, итог не бывает отрицательным.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import OuterRef, Subquery
from django.utils import timezone

from shop.models import Price, Product, Promotion

CENT = Decimal('0.01')


def money(value) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def current_price_subquery():
    return Subquery(
        Price.objects.filter(id_product=OuterRef('pk'), valid_to__isnull=True)
        .order_by('-valid_from')
        .values('product_price')[:1]
    )


def get_current_price(product: Product) -> Decimal | None:
    annotated = getattr(product, 'price_now', None)
    if annotated is not None:
        return annotated
    return product.current_price


def set_price(product: Product, new_price, *, actor=None, reason: str = '') -> Price:
    """Новая версия цены: предыдущая закрывается (история не влияет на оформленные заказы)."""
    new_price = money(new_price)
    if new_price < 0:
        from django.core.exceptions import ValidationError

        raise ValidationError('Цена не может быть отрицательной.')
    now = timezone.now()
    Price.objects.filter(id_product=product, valid_to__isnull=True).update(valid_to=now)
    return Price.objects.create(
        id_product=product, product_price=new_price, id_user=actor, price_reason=reason or None
    )


@dataclass
class Line:
    product: Product
    quantity: int
    price: Decimal
    discount: Decimal = Decimal('0')

    @property
    def subtotal(self) -> Decimal:
        return money(self.price * self.quantity)

    @property
    def total(self) -> Decimal:
        return money(self.subtotal - self.discount)


@dataclass
class Totals:
    lines: list[Line]
    subtotal: Decimal = Decimal('0')
    discount: Decimal = Decimal('0')
    total: Decimal = Decimal('0')
    applied: dict = field(default_factory=dict)  # Promotion -> сумма скидки
    promo_code: str | None = None
    promo_error: str | None = None

    @property
    def quantity(self) -> int:
        return sum(line.quantity for line in self.lines)


def _targets(promo: Promotion):
    cache = getattr(promo, '_targets_cache', None)
    if cache is None:
        cache = (
            set(promo.promotion_products.values_list('id_product_id', flat=True)),
            set(promo.promotion_categories.values_list('id_category_id', flat=True)),
            set(promo.promotion_brands.values_list('id_brand_id', flat=True)),
        )
        promo._targets_cache = cache
    return cache


def _category_chain(product: Product) -> set[int]:
    ids, node = set(), product.id_category
    while node is not None:
        ids.add(node.pk)
        node = node.id_parent
    return ids


def promotion_applies(promo: Promotion, product: Product) -> bool:
    products, categories, brands = _targets(promo)
    if not (products or categories or brands):
        return True  # акция на весь ассортимент
    if product.pk in products:
        return True
    if product.id_brand_id and product.id_brand_id in brands:
        return True
    return bool(categories & _category_chain(product))


def active_promotions(now=None):
    now = now or timezone.now()
    return Promotion.objects.filter(is_active=True, start_at__lte=now, end_at__gte=now)


def validate_promo_code(code: str, lines: list[Line], now=None) -> tuple[Promotion | None, str | None]:
    code = (code or '').strip()
    if not code:
        return None, None
    now = now or timezone.now()
    promo = Promotion.objects.filter(promotion_promo_code__iexact=code).first()
    if not promo or not promo.is_active:
        return None, 'Промокод не найден.'
    if promo.start_at > now:
        return None, 'Промокод ещё не действует.'
    if promo.end_at < now:
        return None, 'Срок действия промокода истёк.'
    if promo.usage_limit is not None and promo.usage_count >= promo.usage_limit:
        return None, 'Лимит использований промокода исчерпан.'
    eligible = [line for line in lines if promotion_applies(promo, line.product)]
    if not eligible:
        return None, 'Промокод не распространяется на товары в корзине.'
    eligible_sum = sum((line.subtotal for line in eligible), Decimal('0'))
    if eligible_sum < promo.promotion_min_sum:
        return None, f'Минимальная сумма для промокода — {promo.promotion_min_sum} ₽.'
    if sum(line.quantity for line in eligible) < promo.promotion_min_qty:
        return None, f'Минимальное количество товаров для промокода — {promo.promotion_min_qty} шт.'
    return promo, None


def _promo_line_discounts(promo: Promotion, lines: list[Line]) -> dict[int, Decimal]:
    """Скидка акции по каждой подходящей позиции (индекс позиции -> сумма)."""
    eligible = [(i, line) for i, line in enumerate(lines) if promotion_applies(promo, line.product)]
    if not eligible:
        return {}
    eligible_sum = sum((line.subtotal for _, line in eligible), Decimal('0'))
    eligible_qty = sum(line.quantity for _, line in eligible)
    if eligible_sum < promo.promotion_min_sum or eligible_qty < promo.promotion_min_qty:
        return {}
    result = {}
    if promo.promotion_type == 'percent':
        pct = min(max(promo.promotion_value, Decimal('0')), Decimal('100'))
        for i, line in eligible:
            result[i] = money(line.subtotal * pct / 100)
    else:
        amount = min(promo.promotion_value, eligible_sum)
        distributed = Decimal('0')
        for n, (i, line) in enumerate(eligible):
            if n == len(eligible) - 1:
                part = amount - distributed
            else:
                part = money(amount * line.subtotal / eligible_sum) if eligible_sum else Decimal('0')
            result[i] = part
            distributed += part
    return result


def calculate(lines: list[Line], promo_code: str | None = None, now=None) -> Totals:
    now = now or timezone.now()
    totals = Totals(lines=lines, promo_code=(promo_code or '').strip() or None)
    auto = {}  # индекс позиции -> (скидка, акция)
    for promo in active_promotions(now).filter(promotion_promo_code__isnull=True):
        for i, value in _promo_line_discounts(promo, lines).items():
            if value > auto.get(i, (Decimal('0'), None))[0]:
                auto[i] = (value, promo)

    code_promo, error = validate_promo_code(promo_code, lines, now) if promo_code else (None, None)
    totals.promo_error = error
    code_discounts = _promo_line_discounts(code_promo, lines) if code_promo else {}

    for i, line in enumerate(lines):
        auto_value, auto_promo = auto.get(i, (Decimal('0'), None))
        code_value = code_discounts.get(i, Decimal('0'))
        parts = []
        if code_promo and code_promo.is_stackable:
            parts = [(auto_value, auto_promo), (code_value, code_promo)]
        elif code_value > auto_value:
            parts = [(code_value, code_promo)]
        else:
            parts = [(auto_value, auto_promo)]
        line_discount = Decimal('0')
        for value, promo in parts:
            if promo is None or value <= 0:
                continue
            value = min(value, line.subtotal - line_discount)
            line_discount += value
            totals.applied[promo] = totals.applied.get(promo, Decimal('0')) + value
        line.discount = money(line_discount)

    totals.subtotal = sum((line.subtotal for line in lines), Decimal('0'))
    totals.discount = sum((line.discount for line in lines), Decimal('0'))
    totals.total = max(Decimal('0'), totals.subtotal - totals.discount)
    if code_promo and code_promo not in totals.applied and not error:
        totals.promo_error = 'Промокод не даёт дополнительной выгоды к действующей акции.'
    return totals
