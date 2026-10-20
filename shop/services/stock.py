"""Складские операции: приход, резерв, списание, возвраты. Всё — в транзакции и с аудитом."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from shop.models import Order, Product, Reservation, Stock, StockMovement
from shop.services.audit import write_audit
from users.models import AuthCredentials


def lock_stock(product: Product) -> Stock:
    """Блокирует строку остатка товара (SELECT … FOR UPDATE), создавая её при отсутствии."""
    Stock.objects.get_or_create(
        id_product=product, defaults={'stock_quantity': 0, 'stock_reserved': 0}
    )
    return Stock.objects.select_for_update().get(id_product=product)


def lock_stocks(products) -> dict[int, Stock]:
    """Блокирует остатки нескольких товаров в порядке id — защита от взаимоблокировок."""
    result = {}
    for product in sorted(products, key=lambda p: p.pk):
        result[product.pk] = lock_stock(product)
    return result


def _record(
    stock: Stock,
    movement_type: str,
    quantity: int,
    *,
    actor: AuthCredentials | None,
    reason: str = '',
    order: Order | None = None,
    document_number: str | None = None,
    expected_quantity: int | None = None,
) -> StockMovement:
    stock.stock_movement_type = movement_type
    history = list(stock.stock_movement_history or [])
    history.append(
        {
            'at': timezone.now().isoformat(timespec='seconds'),
            'type': movement_type,
            'delta': quantity,
            'qty_after': stock.stock_quantity,
            'reserved_after': stock.stock_reserved,
            'by': actor.email if actor else 'system',
        }
    )
    stock.stock_movement_history = history[-50:]
    stock.save()
    return StockMovement.objects.create(
        id_product=stock.id_product,
        movement_type=movement_type,
        movement_quantity=quantity,
        expected_quantity=expected_quantity,
        quantity_after=stock.stock_quantity,
        reserved_after=stock.stock_reserved,
        movement_reason=reason[:500] if reason else None,
        document_number=document_number,
        id_order=order,
        id_user=actor,
    )


@transaction.atomic
def receive_stock(
    product: Product,
    quantity: int,
    *,
    actor: AuthCredentials,
    document_number: str = '',
    expected_quantity: int | None = None,
    reason: str = '',
    request=None,
) -> StockMovement:
    """Приход товара со сверкой фактического количества с учётным (накладной)."""
    if quantity <= 0:
        raise ValidationError('Количество прихода должно быть положительным.')
    stock = lock_stock(product)
    before = {'stock_quantity': stock.stock_quantity}
    stock.stock_quantity += quantity
    note = reason
    if expected_quantity is not None and expected_quantity != quantity:
        note = f'{reason} Расхождение с накладной: ожидалось {expected_quantity}, факт {quantity}.'.strip()
    movement = _record(
        stock, 'receipt', quantity, actor=actor, reason=note,
        document_number=document_number or None, expected_quantity=expected_quantity,
    )
    write_audit(
        user=actor, object_type='stock', object_id=stock.id_stock, action='receipt',
        before=before,
        after={'stock_quantity': stock.stock_quantity, 'received': quantity,
               'expected': expected_quantity, 'document': document_number},
        reason=note, request=request,
    )
    return movement


@transaction.atomic
def adjust_stock(
    product: Product,
    delta: int,
    *,
    actor: AuthCredentials,
    reason: str,
    movement_type: str = 'adjustment',
    request=None,
) -> Stock:
    """Критическая корректировка остатка (только с подтверждением и причиной)."""
    if not reason or not reason.strip():
        raise ValidationError('Укажите причину корректировки.')
    stock = lock_stock(product)
    before = {'stock_quantity': stock.stock_quantity, 'stock_reserved': stock.stock_reserved}
    new_qty = stock.stock_quantity + delta
    if new_qty < 0:
        raise ValidationError('Остаток не может стать отрицательным.')
    if new_qty < stock.stock_reserved:
        raise ValidationError('Нельзя уменьшить остаток ниже зарезервированного количества.')
    stock.stock_quantity = new_qty
    _record(stock, movement_type, delta, actor=actor, reason=reason)
    write_audit(
        user=actor, object_type='stock', object_id=stock.id_stock, action=movement_type,
        before=before,
        after={'stock_quantity': stock.stock_quantity, 'stock_reserved': stock.stock_reserved, 'delta': delta},
        reason=reason, request=request,
    )
    return stock


def reserve(
    product: Product,
    quantity: int,
    *,
    cart=None,
    order: Order | None = None,
    expires_at=None,
) -> Reservation:
    """Резервирует товар. Вызывать внутри transaction.atomic."""
    if quantity <= 0:
        raise ValidationError('Количество должно быть положительным.')
    stock = lock_stock(product)
    available = stock.stock_quantity - stock.stock_reserved
    if quantity > available:
        raise ValidationError(
            f'Недостаточно товара «{product.product_name}» на складе: доступно {max(available, 0)} шт.'
        )
    stock.stock_reserved += quantity
    _record(stock, 'reserve', quantity, actor=None, order=order,
            reason=f'Корзина #{cart.pk}' if cart else '')
    return Reservation.objects.create(
        id_product=product, id_cart=cart, id_order=order,
        reservation_quantity=quantity, expires_at=expires_at,
    )


def change_reservation(reservation: Reservation, new_quantity: int, *, expires_at=None) -> None:
    """Меняет объём активного резерва (увеличение — с проверкой свободного остатка)."""
    stock = lock_stock(reservation.id_product)
    delta = new_quantity - reservation.reservation_quantity
    if delta > 0 and delta > stock.stock_quantity - stock.stock_reserved:
        available = stock.stock_quantity - stock.stock_reserved + reservation.reservation_quantity
        raise ValidationError(
            f'Недостаточно товара «{reservation.id_product.product_name}»: доступно {max(available, 0)} шт.'
        )
    stock.stock_reserved = max(0, stock.stock_reserved + delta)
    if delta:
        _record(stock, 'reserve' if delta > 0 else 'release', delta, actor=None,
                order=reservation.id_order)
    reservation.reservation_quantity = new_quantity
    if expires_at is not None:
        reservation.expires_at = expires_at
    reservation.save(update_fields=['reservation_quantity', 'expires_at'])


def release(reservation: Reservation, *, status: str = 'released', actor=None, reason: str = '') -> None:
    """Снимает активный резерв. Вызывать внутри transaction.atomic."""
    reservation = Reservation.objects.select_for_update().get(pk=reservation.pk)
    if reservation.reservation_status != 'active':
        return
    stock = lock_stock(reservation.id_product)
    stock.stock_reserved = max(0, stock.stock_reserved - reservation.reservation_quantity)
    _record(stock, 'release', -reservation.reservation_quantity, actor=actor,
            order=reservation.id_order, reason=reason or status)
    reservation.reservation_status = status
    reservation.save(update_fields=['reservation_status'])


def release_order_reservations(order: Order, *, actor=None, reason: str = '') -> int:
    count = 0
    for reservation in order.reservations.filter(reservation_status='active'):
        release(reservation, actor=actor, reason=reason)
        count += 1
    return count


@transaction.atomic
def write_off_for_order(order: Order, *, actor: AuthCredentials, request=None) -> None:
    """Списание собранного заказа: остаток и резерв уменьшаются на кол-во позиций."""
    reservations = {
        r.id_product_id: r for r in order.reservations.select_for_update().filter(reservation_status='active')
    }
    items = list(order.items.select_related('id_product'))
    lock_stocks([item.id_product for item in items])
    for item in items:
        stock = lock_stock(item.id_product)
        reservation = reservations.get(item.id_product_id)
        reserved_part = min(reservation.reservation_quantity, item.order_item_quantity) if reservation else 0
        free_needed = item.order_item_quantity - reserved_part
        if free_needed > stock.stock_quantity - stock.stock_reserved:
            raise ValidationError(
                f'Недостаточно остатка для списания «{item.id_product.product_name}».'
            )
        if item.order_item_quantity > stock.stock_quantity:
            raise ValidationError('Остаток не может стать отрицательным.')
        before = {'stock_quantity': stock.stock_quantity, 'stock_reserved': stock.stock_reserved}
        stock.stock_quantity -= item.order_item_quantity
        stock.stock_reserved = max(0, stock.stock_reserved - reserved_part)
        _record(stock, 'write_off', -item.order_item_quantity, actor=actor, order=order,
                reason=f'Сборка заказа {order.order_number}')
        if reservation:
            reservation.reservation_status = 'consumed'
            reservation.save(update_fields=['reservation_status'])
        write_audit(
            user=actor, object_type='stock', object_id=stock.id_stock, action='write_off',
            before=before,
            after={'stock_quantity': stock.stock_quantity, 'stock_reserved': stock.stock_reserved,
                   'quantity': item.order_item_quantity, 'order': order.order_number},
            request=request,
        )


def restore_written_off(order: Order, *, actor=None, reason: str = '') -> None:
    """Обратная операция к списанию — при отмене уже собранного заказа."""
    for item in order.items.select_related('id_product'):
        stock = lock_stock(item.id_product)
        stock.stock_quantity += item.order_item_quantity
        _record(stock, 'cancel_restore', item.order_item_quantity, actor=actor, order=order,
                reason=reason or f'Отмена заказа {order.order_number}')


def return_to_stock(product: Product, quantity: int, *, defect: bool, actor, order=None, reason='') -> None:
    """Возврат товара покупателем: годный — на склад, бракованный — списывается в брак."""
    stock = lock_stock(product)
    if defect:
        _record(stock, 'defect', 0, actor=actor, order=order,
                reason=f'Брак по возврату: {quantity} шт. списано. {reason}'.strip())
    else:
        stock.stock_quantity += quantity
        _record(stock, 'return', quantity, actor=actor, order=order, reason=reason)
