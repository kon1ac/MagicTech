"""Сводная статистика для страниц панели (по доступным разделам роли)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import F, Q
from django.utils import timezone

from users.permissions import has_permission


def users_stats(actor) -> list[dict]:
    if not has_permission(actor.user_role, 'users', 'view'):
        return []
    from users.models import AuthCredentials

    total = AuthCredentials.objects.exclude(user_role='GHOST').count()
    active = AuthCredentials.objects.exclude(user_role='GHOST').filter(is_active=True).count()
    banned = total - active
    customers = AuthCredentials.objects.filter(user_role='CUSTOMER', is_active=True).count()
    return [
        {'label': 'Всего учёток', 'value': total},
        {'label': 'Активных', 'value': active, 'tone': 'accent'},
        {'label': 'Заблокированных', 'value': banned, 'tone': 'danger' if banned else ''},
        {'label': 'Покупателей', 'value': customers},
    ]


def products_stats(actor) -> list[dict]:
    if not has_permission(actor.user_role, 'products', 'view'):
        return []
    from shop.models import Product, Stock

    active = Product.objects.filter(is_active=True).count()
    low = Stock.objects.annotate(avail=F('stock_quantity') - F('stock_reserved')).filter(avail__lte=5).count()
    return [
        {'label': 'Товаров в продаже', 'value': active, 'tone': 'accent'},
        {'label': 'Низкий остаток (≤5)', 'value': low, 'tone': 'warn' if low else ''},
    ]


def stock_stats(actor) -> list[dict]:
    if not has_permission(actor.user_role, 'stock', 'view'):
        return []
    from shop.models import Stock, StockMovement
    from shop.services.reports import stock_turnover

    data = stock_turnover(30)
    rows = sorted(data['rows'], key=lambda r: r['sold'], reverse=True)
    zero = Stock.objects.annotate(avail=F('stock_quantity') - F('stock_reserved')).filter(avail__lte=0).count()
    receipts = StockMovement.objects.filter(
        movement_type='receipt', created_at__gte=timezone.now() - timedelta(days=30)
    ).count()
    top = rows[0]['sku'] if rows and rows[0]['sold'] else '—'
    return [
        {'label': 'SKU без остатка', 'value': zero, 'tone': 'danger' if zero else ''},
        {'label': 'Неликвид (90 дн.)', 'value': data['illiquid'], 'tone': 'warn' if data['illiquid'] else ''},
        {'label': 'Приходов за 30 дн.', 'value': receipts},
        {'label': 'Топ продаж (SKU)', 'value': top, 'tone': 'accent'},
    ]


def orders_stats(actor) -> list[dict]:
    if not has_permission(actor.user_role, 'orders', 'view'):
        return []
    from shop.models import Order
    from users.constants import ORDER_ACTIVE_STATUSES

    active = Order.objects.filter(order_status__in=ORDER_ACTIVE_STATUSES).count()
    today = Order.objects.filter(created_at__date=timezone.localdate()).count()
    return [
        {'label': 'Заказов в работе', 'value': active, 'tone': 'accent'},
        {'label': 'Создано сегодня', 'value': today},
    ]


def reviews_stats(actor) -> list[dict]:
    if not has_permission(actor.user_role, 'reviews', 'view'):
        return []
    from shop.models import Review

    pending = Review.objects.filter(review_type='review', review_status='pending').count()
    return [{'label': 'На модерации', 'value': pending, 'tone': 'warn' if pending else ''}]


def payments_stats(actor) -> list[dict]:
    if not has_permission(actor.user_role, 'payments', 'view'):
        return []
    from shop.models import Payment

    pending = Payment.objects.filter(payment_status='PENDING').count()
    return [{'label': 'Платежей ожидает', 'value': pending, 'tone': 'warn' if pending else ''}]


def promotions_stats(actor) -> list[dict]:
    if not has_permission(actor.user_role, 'promotions', 'view'):
        return []
    from shop.models import Promotion

    now = timezone.now()
    active = Promotion.objects.filter(is_active=True, start_at__lte=now).filter(
        Q(end_at__isnull=True) | Q(end_at__gte=now)
    ).count()
    return [{'label': 'Активных акций', 'value': active, 'tone': 'accent'}]


def audit_stats(actor) -> list[dict]:
    if not has_permission(actor.user_role, 'audit', 'view'):
        return []
    from shop.models import AuditLog

    today = AuditLog.objects.filter(created_at__date=timezone.localdate()).count()
    bans = AuditLog.objects.filter(audit_action='auto_ban').count()
    return [
        {'label': 'Событий сегодня', 'value': today},
        {'label': 'Автобанов всего', 'value': bans, 'tone': 'danger' if bans else ''},
    ]
