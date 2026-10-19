"""Заказы: атомарное оформление, статус-флоу по регламенту, отмена с возвратом резерва."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from shop.models import Cart, Order, OrderItem, OrderPromotion, Product, Promotion, Reservation
from shop.services import pricing, stock as stock_service
from shop.services.audit import write_audit
from users.constants import (
    ORDER_STATUS_FLOW,
    ORDER_STATUS_LABELS,
    ORDER_WRITTEN_OFF_STATUSES,
    PAYMENT_METHOD_LABELS,
)
from users.models import AuthCredentials

logger = logging.getLogger('magictech')


def allowed_transitions(order: Order) -> set[str]:
    """Переходы по регламенту с учётом способа оплаты."""
    allowed = set(ORDER_STATUS_FLOW.get(order.order_status, set()))
    online = order.order_payment_method == 'card_online'
    # PAID выставляет только платёжный контур (веб-хук ЮKassa / ручное подтверждение)
    allowed.discard('PAID')
    if order.order_status == 'NEW' and online:
        allowed.discard('CONFIRMED')  # онлайн-заказ подтверждается только после оплаты
    if 'COMPLETED' in allowed and order.order_payment_status != 'SUCCESS':
        allowed.discard('COMPLETED')  # закрыть можно только оплаченный заказ
    allowed.discard('RETURNED')  # выставляется процессом возврата
    return allowed


def can_transition(current: str, new: str) -> bool:
    return new in ORDER_STATUS_FLOW.get(current, set())


@transaction.atomic
def change_order_status(
    order: Order,
    new_status: str,
    *,
    actor: AuthCredentials | None,
    reason: str = '',
    request=None,
    system: bool = False,
) -> Order:
    """Смена статуса. system=True — переход инициирован сервером (оплата, возврат, таймаут)."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    current = order.order_status
    if current == new_status:
        return order
    permitted = ORDER_STATUS_FLOW.get(current, set()) if system else allowed_transitions(order)
    if new_status not in permitted:
        raise ValidationError(
            f'Нельзя перевести заказ из «{ORDER_STATUS_LABELS.get(current, current)}» '
            f'в «{ORDER_STATUS_LABELS.get(new_status, new_status)}» по регламенту.'
        )
    if new_status == 'CANCELLED' and not system and not reason.strip():
        raise ValidationError('Укажите причину отмены заказа.')

    before = {'order_status': current}
    if new_status == 'CANCELLED':
        if current in ORDER_WRITTEN_OFF_STATUSES:
            stock_service.restore_written_off(order, actor=actor, reason=reason)
        stock_service.release_order_reservations(order, actor=actor, reason='Отмена заказа')
        _cancel_pending_payments(order)
    order.order_status = new_status
    order.save(update_fields=['order_status', 'updated_at'])
    write_audit(
        user=actor, object_type='order', object_id=order.id_order, action='status_change',
        before=before, after={'order_status': new_status}, reason=reason, request=request,
    )
    _notify(order, f'Статус заказа {order.order_number}: {ORDER_STATUS_LABELS.get(new_status, new_status)}')
    return order


def _cancel_pending_payments(order: Order) -> None:
    order.payments.filter(payment_status='PENDING').update(payment_status='FAILED')
    if order.order_payment_status == 'PENDING':
        order.order_payment_status = 'FAILED'
        order.save(update_fields=['order_payment_status'])


def _notify(order: Order, subject: str) -> None:
    email = order.id_user.email

    def send():
        try:
            send_mail(subject, f'{subject}\nСумма: {order.total} ₽', None, [email], fail_silently=True)
        except Exception:  # уведомление не должно ломать бизнес-операцию
            logger.exception('notify failed')

    transaction.on_commit(send)


@transaction.atomic
def checkout(
    cart: Cart,
    *,
    user: AuthCredentials,
    payment_method: str,
    offer_accepted: bool,
    delivery_address: str = '',
    contact_phone: str = '',
    comment: str = '',
    channel: str = 'site',
    external_order_id: str | None = None,
    request=None,
):
    """Атомарно: заказ + резервирование + платёжная транзакция + уведомление.

    При любой ошибке транзакция откатывается целиком, наружу уходит ValidationError
    с человекочитаемым сообщением.
    """
    from shop.services import payments as payment_service

    if payment_method not in PAYMENT_METHOD_LABELS:
        raise ValidationError('Выберите способ оплаты.')
    if not offer_accepted:
        raise ValidationError('Необходимо согласие с условиями оферты.')
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    if cart.cart_status != 'active':
        raise ValidationError('Корзина уже оформлена.')
    items = list(cart.items.select_related('id_product'))
    if not items:
        raise ValidationError('Корзина пуста.')
    stock_service.lock_stocks([item.id_product for item in items])

    lines = []
    for item in items:
        product = Product.objects.select_related('id_category__id_parent__id_parent').get(pk=item.id_product_id)
        if not product.is_active:
            raise ValidationError(f'Товар «{product.product_name}» снят с продажи.')
        price = pricing.get_current_price(product)
        if price is None:
            raise ValidationError(f'У товара «{product.product_name}» нет цены.')
        lines.append(pricing.Line(product=product, quantity=item.cart_item_quantity, price=price))

    if cart.cart_promo_code:
        # блокируем промокод, чтобы параллельные заказы не превысили лимит использований
        Promotion.objects.select_for_update().filter(
            promotion_promo_code__iexact=cart.cart_promo_code
        ).first()
    totals = pricing.calculate(lines, cart.cart_promo_code)
    if totals.promo_error and cart.cart_promo_code:
        raise ValidationError(f'Промокод: {totals.promo_error}')
    if totals.total < Decimal(settings.MAGTECH_MIN_ORDER_TOTAL):
        raise ValidationError(f'Минимальная сумма заказа — {settings.MAGTECH_MIN_ORDER_TOTAL} ₽.')

    online = payment_method == 'card_online'
    due = timezone.now() + timedelta(minutes=settings.MAGTECH_ORDER_PAYMENT_TIMEOUT_MINUTES) if online else None
    order = Order.objects.create(
        order_number=f'TMP-{cart.pk}-{timezone.now().timestamp()}',
        id_user=user,
        order_status='NEW',
        total_items=totals.subtotal,
        discount_total=totals.discount,
        total=totals.total,
        order_payment_method=payment_method,
        order_payment_status='PENDING' if online else 'NOT_PAID',
        order_channel=channel,
        external_order_id=external_order_id,
        order_promo_code=cart.cart_promo_code,
        order_comment=comment or None,
        delivery_address=delivery_address or None,
        contact_phone=contact_phone or None,
        offer_accepted=True,
        payment_due_at=due,
    )
    order.order_number = f'MT-{timezone.localdate():%y%m%d}-{order.id_order:06d}'
    order.save(update_fields=['order_number'])

    for line in lines:
        OrderItem.objects.create(
            id_order=order,
            id_product=line.product,
            order_item_quantity=line.quantity,
            order_item_price=line.price,
            order_item_discount=line.discount,
            order_item_total=line.total,
        )
        Product.objects.filter(pk=line.product.pk).update(sales_count=F('sales_count') + line.quantity)

        # резерв корзины переходит на заказ; если истёк — резервируем заново с проверкой остатка
        reservation = (
            Reservation.objects.select_for_update()
            .filter(id_cart=cart, id_product=line.product, reservation_status='active')
            .first()
        )
        if reservation and reservation.reservation_quantity == line.quantity:
            reservation.id_cart = None
            reservation.id_order = order
            reservation.expires_at = due
            reservation.save(update_fields=['id_cart', 'id_order', 'expires_at'])
        else:
            if reservation:
                stock_service.release(reservation, reason='Перерезервирование при оформлении')
            stock_service.reserve(line.product, line.quantity, order=order, expires_at=due)

    for promo, amount in totals.applied.items():
        OrderPromotion.objects.create(id_order=order, id_promotion=promo, order_promotion_discount=amount)
        if promo.promotion_promo_code:
            Promotion.objects.filter(pk=promo.pk).update(usage_count=F('usage_count') + 1)

    payment = payment_service.create_payment(order, user=user) if online else None

    cart.cart_status = 'ordered'
    cart.save(update_fields=['cart_status', 'updated_at'])
    write_audit(
        user=user, object_type='order', object_id=order.id_order, action='create',
        after={'order_number': order.order_number, 'total': order.total,
               'payment_method': payment_method, 'channel': channel},
        request=request,
    )
    _notify(order, f'Заказ {order.order_number} оформлен')
    return order, payment


@transaction.atomic
def expire_unpaid_orders(now=None) -> int:
    """Cron: отменяет онлайн-заказы, не оплаченные за отведённое время, и снимает их резерв."""
    now = now or timezone.now()
    count = 0
    for order in Order.objects.filter(
        order_status='NEW', order_payment_method='card_online', payment_due_at__lt=now
    ):
        change_order_status(order, 'CANCELLED', actor=None, reason='Истёк срок оплаты', system=True)
        count += 1
    return count


@transaction.atomic
def release_expired_cart_reservations(now=None) -> int:
    """Cron: снимает просроченные резервы корзин."""
    now = now or timezone.now()
    count = 0
    for reservation in Reservation.objects.filter(
        reservation_status='active', id_cart__isnull=False, expires_at__lt=now
    ):
        stock_service.release(reservation, status='expired', reason='Истёк таймаут резерва корзины')
        count += 1
    return count


@transaction.atomic
def confirm_shipment(order: Order, *, actor, tracking_number: str = '', request=None) -> Order:
    """Подтверждение отгрузки (маркетплейс/служба доставки)."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.order_status != 'PACKED':
        raise ValidationError('Отгрузить можно только собранный заказ (PACKED).')
    order.shipped_at = timezone.now()
    order.tracking_number = tracking_number or None
    order.save(update_fields=['shipped_at', 'tracking_number', 'updated_at'])
    write_audit(user=actor, object_type='order', object_id=order.id_order, action='shipped',
                after={'tracking_number': tracking_number}, request=request)
    if order.order_payment_status == 'SUCCESS':
        change_order_status(order, 'COMPLETED', actor=actor, reason='Отгружен', request=request, system=True)
    return order
