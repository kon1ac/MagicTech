"""Складские операции с проверкой остатков."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from shop.models import Product, Stock
from shop.services.audit import write_audit
from users.models import AuthCredentials


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
    stock, _ = Stock.objects.select_for_update().get_or_create(
        id_product=product,
        defaults={'stock_quantity': 0, 'stock_reserved': 0},
    )
    before = {
        'stock_quantity': stock.stock_quantity,
        'stock_reserved': stock.stock_reserved,
        'reason': reason,
    }
    new_qty = stock.stock_quantity + delta
    if new_qty < 0:
        raise ValidationError('Остаток не может стать отрицательным.')
    if new_qty < stock.stock_reserved:
        raise ValidationError('Нельзя уменьшить остаток ниже зарезервированного количества.')

    stock.stock_quantity = new_qty
    stock.stock_movement_type = movement_type
    history = list(stock.stock_movement_history or [])
    history.append(
        {
            'delta': delta,
            'type': movement_type,
            'reason': reason,
            'by': actor.email,
            'qty_after': new_qty,
        }
    )
    stock.stock_movement_history = history[-50:]
    stock.save(
        update_fields=[
            'stock_quantity',
            'stock_movement_type',
            'stock_movement_history',
            'updated_at',
        ]
    )

    write_audit(
        user=actor,
        object_type='stock',
        object_id=stock.id_stock,
        action='adjustment',
        before=before,
        after={
            'stock_quantity': stock.stock_quantity,
            'stock_reserved': stock.stock_reserved,
            'delta': delta,
            'reason': reason,
        },
        request=request,
    )
    return stock


@transaction.atomic
def write_off_for_order_item(
    product: Product,
    quantity: int,
    *,
    actor: AuthCredentials,
    order_id: int,
    request=None,
) -> Stock:
    stock = Stock.objects.select_for_update().filter(id_product=product).first()
    if not stock:
        raise ValidationError('Остаток для товара не найден.')
    available = stock.stock_quantity - stock.stock_reserved
    if quantity > available:
        raise ValidationError('Недостаточно свободного остатка для списания.')

    before = {'stock_quantity': stock.stock_quantity, 'stock_reserved': stock.stock_reserved}
    stock.stock_quantity -= quantity
    stock.stock_reserved = max(0, stock.stock_reserved - quantity)
    stock.stock_movement_type = 'write_off'
    stock.save(update_fields=['stock_quantity', 'stock_reserved', 'stock_movement_type', 'updated_at'])

    write_audit(
        user=actor,
        object_type='stock',
        object_id=stock.id_stock,
        action='write_off',
        before=before,
        after={
            'stock_quantity': stock.stock_quantity,
            'quantity': quantity,
            'order_id': order_id,
        },
        request=request,
    )
    return stock
