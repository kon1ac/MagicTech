"""Корзина: серверная проверка остатка и предварительный резерв на 15–30 минут."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from shop.models import Cart, CartItem, Product, Reservation
from shop.services import pricing, stock as stock_service


def reservation_deadline():
    return timezone.now() + timedelta(minutes=settings.MAGTECH_CART_RESERVATION_MINUTES)


def get_cart(*, user=None, session_key: str | None = None, create: bool = True) -> Cart | None:
    qs = Cart.objects.filter(cart_status='active')
    cart = None
    if user is not None:
        cart = qs.filter(id_user=user).order_by('-updated_at').first()
    elif session_key:
        cart = qs.filter(cart_session_id=session_key, id_user__isnull=True).first()
    if cart is None and create:
        cart = Cart.objects.create(id_user=user, cart_session_id=None if user else session_key)
    return cart


@transaction.atomic
def merge_session_cart(session_key: str | None, user) -> None:
    """При входе покупателя переносит гостевую корзину в его аккаунт."""
    if not session_key:
        return
    guest = Cart.objects.filter(
        cart_status='active', cart_session_id=session_key, id_user__isnull=True
    ).first()
    if not guest:
        return
    target = get_cart(user=user)
    for item in guest.items.select_related('id_product'):
        try:
            add_item(target, item.id_product, item.cart_item_quantity)
        except ValidationError:
            pass
    clear(guest, status='merged')


def _active_reservation(cart: Cart, product: Product) -> Reservation | None:
    return (
        Reservation.objects.select_for_update()
        .filter(id_cart=cart, id_product=product, reservation_status='active')
        .first()
    )


@transaction.atomic
def set_quantity(cart: Cart, product: Product, quantity: int) -> CartItem | None:
    if quantity < 0:
        raise ValidationError('Количество не может быть отрицательным.')
    if quantity > 999:
        raise ValidationError('Слишком большое количество.')
    item = CartItem.objects.select_for_update().filter(id_cart=cart, id_product=product).first()
    reservation = _active_reservation(cart, product)
    if quantity == 0:
        if reservation:
            stock_service.release(reservation, reason='Удалено из корзины')
        if item:
            item.delete()
        cart.save(update_fields=['updated_at'])
        return None

    if not product.is_active:
        raise ValidationError('Товар снят с продажи.')
    price = pricing.get_current_price(product)
    if price is None:
        raise ValidationError('У товара не задана цена.')

    deadline = reservation_deadline()
    if reservation:
        stock_service.change_reservation(reservation, quantity, expires_at=deadline)
    else:
        stock_service.reserve(product, quantity, cart=cart, expires_at=deadline)
    # продлеваем резервы остальных позиций — корзина «живая»
    cart.reservations.filter(reservation_status='active').update(expires_at=deadline)

    if item:
        item.cart_item_quantity = quantity
        item.cart_item_price_snapshot = price
        item.save(update_fields=['cart_item_quantity', 'cart_item_price_snapshot'])
    else:
        item = CartItem.objects.create(
            id_cart=cart, id_product=product, cart_item_quantity=quantity, cart_item_price_snapshot=price
        )
    cart.save(update_fields=['updated_at'])
    return item


def add_item(cart: Cart, product: Product, quantity: int = 1) -> CartItem | None:
    if quantity <= 0:
        raise ValidationError('Количество должно быть положительным.')
    existing = CartItem.objects.filter(id_cart=cart, id_product=product).first()
    current = existing.cart_item_quantity if existing else 0
    return set_quantity(cart, product, current + quantity)


@transaction.atomic
def clear(cart: Cart, *, status: str = 'active') -> None:
    for reservation in cart.reservations.filter(reservation_status='active'):
        stock_service.release(reservation, reason='Очистка корзины')
    cart.items.all().delete()
    cart.cart_status = status
    cart.save(update_fields=['cart_status', 'updated_at'])


def cart_lines(cart: Cart) -> list[pricing.Line]:
    lines = []
    for item in cart.items.select_related('id_product__id_category__id_parent__id_parent', 'id_product__id_brand'):
        price = pricing.get_current_price(item.id_product)
        if price is None:
            continue
        lines.append(pricing.Line(product=item.id_product, quantity=item.cart_item_quantity, price=price))
    return lines


def totals(cart: Cart) -> pricing.Totals:
    return pricing.calculate(cart_lines(cart), cart.cart_promo_code)


def reservation_expires_at(cart: Cart):
    reservation = cart.reservations.filter(reservation_status='active').order_by('expires_at').first()
    return reservation.expires_at if reservation else None
