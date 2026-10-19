"""Возвраты: NEW → IN_REVIEW → APPROVED/REJECTED → RETURNED_TO_WAREHOUSE → REFUNDED/REPLACED.

После одобрения заявка блокируется: изменения только аудиторской правкой с причиной и новой версией.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from shop.models import Order, OrderItem, Return, ReturnItem, ReturnReason
from shop.services import payments as payment_service
from shop.services import stock as stock_service
from shop.services.audit import write_audit
from shop.services.pricing import money
from users.constants import RETURN_LOCKED_STATUSES, RETURN_STATUS_FLOW, RETURN_STATUS_LABELS


def returnable_quantity(order_item: OrderItem) -> int:
    returned = (
        ReturnItem.objects.filter(id_order_item=order_item)
        .exclude(id_return__return_status='REJECTED')
        .aggregate(s=Sum('return_item_quantity'))['s']
        or 0
    )
    return order_item.order_item_quantity - returned


@transaction.atomic
def create_return(
    order: Order,
    *,
    user,
    reason: ReturnReason | None,
    description: str,
    quantities: dict[int, int],
    photo=None,
    actor=None,
    request=None,
) -> Return:
    """quantities: {id_order_item: кол-во}. actor — сотрудник, если заявку заводит администратор."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.order_status != 'COMPLETED':
        raise ValidationError('Возврат оформляется только по завершённому заказу.')
    if order.id_user_id != user.pk:
        raise ValidationError('Заказ принадлежит другому покупателю.')
    chosen = {int(k): int(v) for k, v in quantities.items() if int(v) > 0}
    if not chosen:
        raise ValidationError('Выберите хотя бы один товар для возврата.')
    ret = Return.objects.create(
        id_order=order, id_user=user, id_reason=reason,
        return_reason=reason.reason_name if reason else None,
        return_description=description or None, return_photo=photo,
    )
    total = Decimal('0')
    for item_id, qty in chosen.items():
        item = OrderItem.objects.filter(pk=item_id, id_order=order).first()
        if not item:
            raise ValidationError('Позиция не относится к заказу.')
        if qty > returnable_quantity(item):
            raise ValidationError(f'Нельзя вернуть больше, чем куплено: «{item.id_product.product_name}».')
        amount = money(item.order_item_total / item.order_item_quantity * qty)
        ReturnItem.objects.create(
            id_return=ret, id_order_item=item, return_item_quantity=qty,
            return_item_refund_amount=amount, is_defect=bool(reason and reason.is_defect),
        )
        total += amount
    ret.refund_amount = total
    ret.save(update_fields=['refund_amount'])
    write_audit(user=actor or user, object_type='return', object_id=ret.id_return, action='create',
                after={'order': order.order_number, 'amount': total, 'reason': ret.return_reason},
                request=request)
    return ret


@transaction.atomic
def change_return_status(ret: Return, new_status: str, *, actor, decision: str = '', request=None) -> Return:
    ret = Return.objects.select_for_update().get(pk=ret.pk)
    current = ret.return_status
    if new_status not in RETURN_STATUS_FLOW.get(current, set()):
        raise ValidationError(
            f'Нельзя перевести возврат из «{RETURN_STATUS_LABELS.get(current)}» '
            f'в «{RETURN_STATUS_LABELS.get(new_status, new_status)}».'
        )
    if new_status in {'APPROVED', 'REJECTED'} and not decision.strip():
        raise ValidationError('Укажите решение по заявке.')
    order = ret.id_order

    if new_status == 'RETURNED_TO_WAREHOUSE':
        for item in ret.items.select_related('id_order_item__id_product'):
            stock_service.return_to_stock(
                item.id_order_item.id_product, item.return_item_quantity, defect=item.is_defect,
                actor=actor, order=order, reason=f'Возврат #{ret.pk}',
            )
    elif new_status == 'REFUNDED':
        payment = order.payments.filter(payment_status__in=['SUCCESS', 'PARTIALLY_REFUNDED']).first()
        if not payment:
            raise ValidationError('По заказу нет успешного платежа для возврата денег.')
        payment_service.refund(payment, ret.refund_amount, actor=actor,
                               reason=f'Возврат #{ret.pk}', request=request)
        ret.refund_commission = payment_service.commission_for(ret.refund_amount) \
            if payment.payment_provider == 'yookassa' else Decimal('0')

    if new_status in {'REFUNDED', 'REPLACED'} and _is_full_return(order):
        from shop.services.orders import change_order_status

        change_order_status(order, 'RETURNED', actor=actor, reason=f'Возврат #{ret.pk}',
                            request=request, system=True)

    before = {'return_status': current}
    ret.return_status = new_status
    if decision:
        ret.return_decision = decision
    if new_status in {'APPROVED', 'REJECTED'}:
        ret.decided_by = actor
        ret.decided_at = timezone.now()
    ret.is_locked = new_status in RETURN_LOCKED_STATUSES
    ret.save()
    write_audit(user=actor, object_type='return', object_id=ret.id_return, action='status_change',
                before=before, after={'return_status': new_status}, reason=decision, request=request)
    return ret


def _is_full_return(order: Order) -> bool:
    for item in order.items.all():
        returned = (
            ReturnItem.objects.filter(id_order_item=item, id_return__return_status__in=[
                'APPROVED', 'RETURNED_TO_WAREHOUSE', 'REFUNDED', 'REPLACED'])
            .aggregate(s=Sum('return_item_quantity'))['s'] or 0
        )
        if returned < item.order_item_quantity:
            return False
    return True


@transaction.atomic
def edit_return(ret: Return, *, actor, reason: str, changes: dict, request=None) -> Return:
    """Правка заявки. Заблокированную — только аудиторской правкой с причиной; версия растёт."""
    ret = Return.objects.select_for_update().get(pk=ret.pk)
    if ret.is_locked and not reason.strip():
        raise ValidationError('Заявка утверждена: правка возможна только с указанием причины (аудит).')
    allowed = {'return_description', 'refund_amount', 'return_decision'}
    before = {k: getattr(ret, k) for k in changes if k in allowed}
    for key, value in changes.items():
        if key in allowed:
            setattr(ret, key, value)
    if 'refund_amount' in changes and ret.refund_amount < 0:
        raise ValidationError('Сумма возврата не может быть отрицательной.')
    ret.version += 1
    ret.save()
    write_audit(user=actor, object_type='return', object_id=ret.id_return,
                action='audit_edit' if ret.is_locked else 'update',
                before=before, after={**{k: getattr(ret, k) for k in before}, 'version': ret.version},
                reason=reason, request=request)
    return ret
