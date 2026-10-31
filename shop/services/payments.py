"""Платежи: имитация ЮKassa (создание платежа, веб-хук), ручное подтверждение, возвраты.

Каждая транзакция имеет уникальный payment_uid, все запросы/ответы пишутся в payment_logs,
статусы: PENDING, SUCCESS, FAILED, REFUNDED (PARTIALLY_REFUNDED — частичный возврат).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from shop.models import Order, Payment, PaymentLog
from shop.services.audit import write_audit
from shop.services.pricing import money


def commission_for(amount: Decimal) -> Decimal:
    return money(Decimal(amount) * Decimal(str(settings.MAGTECH_YOOKASSA_COMMISSION_PCT)) / 100)


def sign(body: bytes) -> str:
    secret = settings.MAGTECH_YOOKASSA_WEBHOOK_SECRET.encode()
    return hmac.new(secret, body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str | None) -> bool:
    """Подпись обязательна: пустой/отсутствующий заголовок отклоняется до сравнения."""
    if not signature:
        return False
    return hmac.compare_digest(sign(body), signature)


def _safe_payload(payload):
    """Готовит payload к записи в payment_logs.

    Тело веб-хука приходит извне и ничем не ограничено, поэтому payload
    прогоняется через JSON round-trip: это одновременно и валидация
    (несериализуемое значение вроде модели или Decimal не уронит обработку
    платежа), и проверка размера (иначе один «щедрый» запрос раздул бы
    таблицу payment_logs).
    """
    if payload is None:
        return None
    try:
        text = json.dumps(payload, ensure_ascii=False, cls=DjangoJSONEncoder, default=str)
    except (TypeError, ValueError):
        return {'unserializable': str(type(payload))}
    limit = settings.MAGTECH_PAYMENT_LOG_MAX_BYTES
    if len(text.encode('utf-8')) > limit:
        return {'truncated': True, 'size': len(text), 'preview': text[:limit]}
    return json.loads(text)


def log(payment: Payment, direction: str, payload, http_status: int | None = None) -> None:
    PaymentLog.objects.create(
        id_payment=payment, log_direction=direction, log_payload=_safe_payload(payload),
        http_status=http_status,
    )


def create_payment(order: Order, *, user=None) -> Payment:
    """Создание платежа в шлюзе (имитация запроса POST /v3/payments)."""
    payment = Payment.objects.create(
        id_order=order,
        payment_provider='yookassa',
        payment_method='bank_card',
        payment_amount=order.total,
        payment_status='PENDING',
        id_user=user,
    )
    payment.external_id = f'yk-{payment.payment_uid.hex[:24]}'
    payment.save(update_fields=['external_id'])
    request_payload = {
        'amount': {'value': str(order.total), 'currency': 'RUB'},
        'capture': True,
        'confirmation': {'type': 'redirect', 'return_url': f'/account/orders/{order.order_number}/'},
        'description': f'Заказ {order.order_number}',
        'metadata': {'order_number': order.order_number, 'payment_uid': str(payment.payment_uid)},
    }
    log(payment, 'request', request_payload)
    log(payment, 'response', {
        'id': payment.external_id, 'status': 'pending',
        'confirmation': {'confirmation_url': f'/pay/{payment.payment_uid}/'},
    }, 200)
    return payment


def build_webhook(payment: Payment, event: str) -> bytes:
    """Тело уведомления в формате ЮKassa — используется страницей-имитацией и тестами."""
    status = 'succeeded' if event == 'payment.succeeded' else 'canceled'
    return json.dumps({
        'type': 'notification',
        'event': event,
        'object': {
            'id': payment.external_id,
            'status': status,
            'amount': {'value': str(payment.payment_amount), 'currency': payment.payment_currency},
            'payment_method': {'type': 'bank_card', 'card': {'last4': '4242', 'card_type': 'MIR'}},
            'metadata': {'payment_uid': str(payment.payment_uid)},
        },
    }, ensure_ascii=False).encode()


@transaction.atomic
def process_webhook(body: bytes, signature: str | None, *, request=None) -> Payment:
    """Обработка callback ЮKassa. Идемпотентна: повторное уведомление ничего не меняет."""
    if not verify_signature(body, signature):
        raise PermissionError('Неверная подпись уведомления.')
    try:
        data = json.loads(body)
        obj = data['object']
        event = data['event']
    except (ValueError, KeyError, TypeError) as exc:
        raise ValidationError('Некорректное тело уведомления.') from exc
    payment = Payment.objects.select_for_update().filter(external_id=obj.get('id')).first()
    if not payment:
        raise ValidationError('Платёж не найден.')
    log(payment, 'callback', data, 200)
    if payment.payment_status != 'PENDING':
        return payment  # идемпотентность
    if Decimal(str(obj.get('amount', {}).get('value', '0'))) != payment.payment_amount:
        raise ValidationError('Сумма уведомления не совпадает с суммой платежа.')
    if event == 'payment.succeeded':
        _mark_success(payment, requisites=obj.get('payment_method'), actor=None, request=request,
                      reason='Веб-хук ЮKassa')
    elif event == 'payment.canceled':
        _mark_failed(payment, request=request)
    else:
        raise ValidationError(f'Неизвестное событие: {event}')
    return payment


def _mark_success(payment: Payment, *, requisites=None, actor=None, request=None, reason='') -> None:
    from shop.services.orders import change_order_status

    order = Order.objects.select_for_update().get(pk=payment.id_order_id)
    if order.order_status == 'CANCELLED':
        raise ValidationError('Заказ уже отменён — оплату нужно вернуть покупателю.')
    payment.payment_status = 'SUCCESS'
    payment.paid_at = timezone.now()
    payment.payment_commission = commission_for(payment.payment_amount) if payment.payment_provider == 'yookassa' else 0
    payment.payment_requisites = requisites
    payment.save()
    order.order_payment_status = 'SUCCESS'
    order.paid_at = payment.paid_at
    order.save(update_fields=['order_payment_status', 'paid_at', 'updated_at'])
    # оплаченный заказ больше не ограничен таймаутом — резерв бессрочный до сборки
    order.reservations.filter(reservation_status='active').update(expires_at=None)
    if order.order_status == 'NEW':
        change_order_status(order, 'PAID', actor=actor, reason=reason, request=request, system=True)
    write_audit(user=actor, object_type='payment', object_id=payment.id_payment, action='success',
                after={'amount': payment.payment_amount, 'order': order.order_number}, reason=reason,
                request=request)


def _mark_failed(payment: Payment, *, request=None) -> None:
    from shop.services.orders import change_order_status

    payment.payment_status = 'FAILED'
    payment.save(update_fields=['payment_status', 'updated_at'])
    order = payment.id_order
    order.order_payment_status = 'FAILED'
    order.save(update_fields=['order_payment_status', 'updated_at'])
    if order.order_status == 'NEW':
        # заказ + платёж + снятие резерва — в одной транзакции
        change_order_status(order, 'CANCELLED', actor=None, reason='Оплата отклонена', request=request,
                            system=True)
    write_audit(user=None, object_type='payment', object_id=payment.id_payment, action='failed',
                request=request)


@transaction.atomic
def confirm_manually(payment: Payment, *, actor, reason: str, request=None) -> Payment:
    """Fallback: ручное подтверждение, если веб-хук не дошёл (сверено по выписке)."""
    if not reason.strip():
        raise ValidationError('Укажите основание ручного подтверждения.')
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.payment_status != 'PENDING':
        raise ValidationError('Подтвердить можно только платёж в статусе PENDING.')
    log(payment, 'manual', {'by': actor.email, 'reason': reason})
    _mark_success(payment, actor=actor, request=request, reason=f'Ручное подтверждение: {reason}')
    return payment


@transaction.atomic
def register_marketplace_payment(order: Order, *, marketplace: str, actor=None, request=None) -> Payment:
    """Заказ с маркетплейса оплачен на стороне площадки — фиксируем поступление."""
    payment = Payment.objects.create(
        id_order=order, payment_provider=f'marketplace:{marketplace}'[:30], payment_method='marketplace',
        payment_amount=order.total, payment_status='PENDING', id_user=actor,
    )
    log(payment, 'callback', {'marketplace': marketplace, 'external_order_id': order.external_order_id})
    _mark_success(payment, actor=actor, request=request, reason=f'Оплата на маркетплейсе {marketplace}')
    return payment


@transaction.atomic
def mark_cash_on_delivery_paid(order: Order, *, actor, request=None) -> Payment:
    """Оплата при получении — отмечается администратором."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.order_payment_method != 'cash_on_delivery':
        raise ValidationError('Заказ оплачивается онлайн.')
    if order.order_payment_status == 'SUCCESS':
        raise ValidationError('Заказ уже оплачен.')
    if order.order_status in {'CANCELLED', 'RETURNED'}:
        raise ValidationError('Заказ отменён.')
    payment = Payment.objects.create(
        id_order=order, payment_provider='cash', payment_method='cash_on_delivery',
        payment_amount=order.total, payment_status='PENDING', id_user=actor,
    )
    log(payment, 'manual', {'by': actor.email, 'event': 'cash_on_delivery'})
    _mark_success(payment, actor=actor, request=request, reason='Оплата при получении')
    return payment


@transaction.atomic
def refund(payment: Payment, amount, *, actor, reason: str, request=None) -> Payment:
    """Полный/частичный возврат с пересчётом комиссии шлюза."""
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    amount = money(amount)
    if payment.payment_status not in {'SUCCESS', 'PARTIALLY_REFUNDED'}:
        raise ValidationError('Возврат возможен только по успешному платежу.')
    already = payment.payment_refund_amount or Decimal('0')
    if amount <= 0 or amount > payment.payment_amount - already:
        raise ValidationError(f'Сумма возврата должна быть от 0,01 до {payment.payment_amount - already} ₽.')
    if not reason.strip():
        raise ValidationError('Укажите причину возврата.')
    before = {'status': payment.payment_status, 'refunded': already}
    payment.payment_refund_amount = already + amount
    payment.payment_status = (
        'REFUNDED' if payment.payment_refund_amount >= payment.payment_amount else 'PARTIALLY_REFUNDED'
    )
    payment.save()
    # ЮKassa не возвращает комиссию: потеря магазина пропорциональна возвращённой доле
    lost_commission = money(payment.payment_commission * amount / payment.payment_amount)
    log(payment, 'request', {'refund': {'amount': str(amount), 'reason': reason}})
    log(payment, 'response', {'status': 'succeeded', 'commission_not_returned': str(lost_commission)}, 200)
    order = payment.id_order
    order.order_payment_status = payment.payment_status
    order.save(update_fields=['order_payment_status', 'updated_at'])
    write_audit(user=actor, object_type='payment', object_id=payment.id_payment, action='refund',
                before=before,
                after={'status': payment.payment_status, 'refunded': payment.payment_refund_amount,
                       'amount': amount, 'commission_lost': lost_commission},
                reason=reason, request=request)
    return payment
