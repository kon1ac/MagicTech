"""Бизнес-логика статусов заказов."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from shop.models import Order, Stock
from shop.services.audit import write_audit
from users.constants import ORDER_STATUS_FLOW
from users.models import AuthCredentials


def can_transition(current: str, new: str) -> bool:
    return new in ORDER_STATUS_FLOW.get(current, set())


@transaction.atomic
def change_order_status(
    order: Order,
    new_status: str,
    *,
    actor: AuthCredentials,
    reason: str = '',
    request=None,
) -> Order:
    current = order.order_status
    if current == new_status:
        return order
    if not can_transition(current, new_status):
        raise ValidationError(
            f'Нельзя перевести заказ из «{current}» в «{new_status}» по регламенту.'
        )

    before = {'order_status': current, 'reason': reason}
    order.order_status = new_status
    if new_status == 'CANCELLED':
        _release_reservations(order)
    order.save(update_fields=['order_status', 'updated_at'])

    write_audit(
        user=actor,
        object_type='order',
        object_id=order.id_order,
        action='status_change',
        before=before,
        after={'order_status': new_status, 'reason': reason},
        request=request,
    )
    return order


def _release_reservations(order: Order) -> None:
    for item in order.items.select_related('id_product').all():
        stock = Stock.objects.select_for_update().filter(id_product=item.id_product).first()
        if not stock:
            continue
        release = min(stock.stock_reserved, item.order_item_quantity)
        stock.stock_reserved = max(0, stock.stock_reserved - release)
        stock.save(update_fields=['stock_reserved', 'updated_at'])
