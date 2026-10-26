"""Управленческие и операционные отчёты. Определения метрик — в docstring каждой функции."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Max, Sum
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncWeek
from django.utils import timezone

from shop.models import Order, OrderItem, Payment, ReturnItem, Stock, StockMovement
from users.constants import ORDER_STATUS_LABELS

ZERO = Decimal('0')
MONEY = DecimalField(max_digits=14, decimal_places=2)
TRUNC = {'day': TruncDay, 'week': TruncWeek, 'month': TruncMonth}
SALE_STATUSES = ['PAID', 'CONFIRMED', 'ASSEMBLY', 'PACKED', 'COMPLETED']


def net_revenue():
    """Фактические поступления за всё время: сумма успешных платежей минус оформленные возвраты.

    Полностью возвращённый платёж (REFUNDED) даёт ноль — возврат равен сумме платежа,
    поэтому статус REFUNDED намеренно включён в выборку, а не исключён.
    """
    agg = Payment.objects.filter(
        payment_status__in=['SUCCESS', 'PARTIALLY_REFUNDED', 'REFUNDED']
    ).aggregate(
        gross=Coalesce(Sum('payment_amount'), ZERO, output_field=MONEY),
        refunded=Coalesce(Sum('payment_refund_amount'), ZERO, output_field=MONEY),
    )
    return agg['gross'] - agg['refunded']


def period_bounds(params):
    today = timezone.localdate()
    try:
        date_from = timezone.datetime.fromisoformat(params.get('from')).date() if params.get('from') else today - timedelta(days=89)
        date_to = timezone.datetime.fromisoformat(params.get('to')).date() if params.get('to') else today
    except ValueError:
        date_from, date_to = today - timedelta(days=89), today
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return date_from, date_to


def sales_by_period(date_from, date_to, group='day'):
    """Продажи: заказы в статусах «оплачен…завершён» (без отменённых и возвращённых).
    Выручка = сумма total заказов, средний чек = выручка / число заказов."""
    trunc = TRUNC.get(group, TruncDay)
    rows = (
        Order.objects.filter(order_status__in=SALE_STATUSES, created_at__date__gte=date_from,
                             created_at__date__lte=date_to)
        .annotate(period=trunc('created_at')).values('period')
        .annotate(revenue=Coalesce(Sum('total'), ZERO, output_field=MONEY), orders=Count('id_order'))
        .order_by('period')
    )
    result = []
    for row in rows:
        avg = (row['revenue'] / row['orders']).quantize(Decimal('0.01')) if row['orders'] else ZERO
        result.append({'period': timezone.localtime(row['period']).date() if hasattr(row['period'], 'tzinfo') else row['period'],
                       'revenue': row['revenue'], 'orders': row['orders'], 'avg_check': avg})
    total_rev = sum((r['revenue'] for r in result), ZERO)
    total_orders = sum(r['orders'] for r in result)
    return {
        'rows': result,
        'total_revenue': total_rev,
        'total_orders': total_orders,
        'avg_check': (total_rev / total_orders).quantize(Decimal('0.01')) if total_orders else ZERO,
    }


def top_products(date_from, date_to, by='revenue', limit=15):
    """ТОП товаров. Выручка = Σ order_item_total; маржа = выручка − себестоимость × кол-во;
    возвраты = Σ возвращённых штук (заявки не в статусе REJECTED)."""
    rows = (
        OrderItem.objects.filter(id_order__order_status__in=SALE_STATUSES + ['RETURNED'],
                                 id_order__created_at__date__gte=date_from, id_order__created_at__date__lte=date_to)
        .values('id_product', 'id_product__product_sku', 'id_product__product_name')
        .annotate(
            revenue=Coalesce(Sum('order_item_total'), ZERO, output_field=MONEY),
            qty=Coalesce(Sum('order_item_quantity'), 0),
            cost=Coalesce(Sum(ExpressionWrapper(F('order_item_quantity') * F('id_product__cost_price'),
                                                output_field=MONEY)), ZERO, output_field=MONEY),
        )
    )
    returns = dict(
        ReturnItem.objects.exclude(id_return__return_status='REJECTED')
        .filter(id_return__created_at__date__gte=date_from, id_return__created_at__date__lte=date_to)
        .values('id_order_item__id_product').annotate(s=Sum('return_item_quantity'))
        .values_list('id_order_item__id_product', 's')
    )
    data = []
    for row in rows:
        margin = row['revenue'] - row['cost']
        data.append({'sku': row['id_product__product_sku'], 'name': row['id_product__product_name'],
                     'revenue': row['revenue'], 'qty': row['qty'], 'margin': margin,
                     'margin_pct': (margin / row['revenue'] * 100).quantize(Decimal('0.1')) if row['revenue'] else ZERO,
                     'returns': returns.get(row['id_product'], 0)})
    key = {'revenue': 'revenue', 'qty': 'qty', 'margin': 'margin', 'returns': 'returns'}.get(by, 'revenue')
    data.sort(key=lambda r: r[key], reverse=True)
    return data[:limit]


def financial(date_from, date_to):
    """Финансовый отчёт. Начислено = Σ total заказов (кроме отменённых); оплачено = Σ успешных платежей
    по дате оплаты; возвраты = Σ payment_refund_amount; комиссии = Σ комиссий шлюза; нетто = оплаты − возвраты − комиссии."""
    orders = Order.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to).exclude(order_status='CANCELLED')
    payments = Payment.objects.filter(paid_at__date__gte=date_from, paid_at__date__lte=date_to)
    agg = payments.aggregate(
        paid=Coalesce(Sum('payment_amount'), ZERO, output_field=MONEY),
        refunds=Coalesce(Sum('payment_refund_amount'), ZERO, output_field=MONEY),
        commission=Coalesce(Sum('payment_commission'), ZERO, output_field=MONEY),
    )
    accrued = orders.aggregate(s=Coalesce(Sum('total'), ZERO, output_field=MONEY))['s']
    by_provider = list(payments.values('payment_provider').annotate(
        amount=Coalesce(Sum('payment_amount'), ZERO, output_field=MONEY), cnt=Count('id_payment')).order_by('payment_provider'))
    return {'accrued': accrued, **agg, 'net': agg['paid'] - agg['refunds'] - agg['commission'],
            'by_provider': by_provider}


def order_statuses(now=None):
    """Статусы заказов. «Задержан» — активный заказ без движения > 3 дней;
    «просрочен» — онлайн-заказ, не оплаченный к payment_due_at."""
    now = now or timezone.now()
    counts = dict(Order.objects.values('order_status').annotate(c=Count('id_order')).values_list('order_status', 'c'))
    delayed = Order.objects.filter(order_status__in=['CONFIRMED', 'ASSEMBLY', 'PACKED'],
                                   updated_at__lt=now - timedelta(days=3)).count()
    overdue = Order.objects.filter(order_status='NEW', order_payment_method='card_online', payment_due_at__lt=now).count()
    return {
        'by_status': [{'code': c, 'label': ORDER_STATUS_LABELS[c], 'count': counts.get(c, 0)} for c in ORDER_STATUS_LABELS],
        'in_work': sum(counts.get(c, 0) for c in ['NEW', 'PAID', 'CONFIRMED', 'ASSEMBLY']),
        'packed': counts.get('PACKED', 0),
        'completed': counts.get('COMPLETED', 0),
        'delayed': delayed,
        'overdue': overdue,
    }


def stock_turnover(days=30):
    """Остатки и обороты. Продано = Σ списаний за N дней; оборачиваемость (дней) = остаток / (продано / N);
    неликвид — товар с остатком > 0 без списаний 90 дней."""
    since = timezone.now() - timedelta(days=days)
    sold = dict(StockMovement.objects.filter(movement_type='write_off', created_at__gte=since)
                .values('id_product').annotate(s=Sum('movement_quantity')).values_list('id_product', 's'))
    last_sale = dict(StockMovement.objects.filter(movement_type='write_off').values('id_product')
                     .annotate(m=Max('created_at')).values_list('id_product', 'm'))
    cutoff = timezone.now() - timedelta(days=90)
    rows = []
    for stock in Stock.objects.select_related('id_product').order_by('id_product__product_sku'):
        qty_sold = -(sold.get(stock.id_product_id) or 0)
        turnover = round(stock.stock_quantity / (qty_sold / days), 1) if qty_sold else None
        last = last_sale.get(stock.id_product_id)
        rows.append({
            'sku': stock.id_product.product_sku, 'name': stock.id_product.product_name,
            'quantity': stock.stock_quantity, 'reserved': stock.stock_reserved,
            'available': stock.stock_quantity - stock.stock_reserved, 'sold': qty_sold,
            'turnover_days': turnover,
            'illiquid': stock.stock_quantity > 0 and (last is None or last < cutoff),
        })
    return {
        'rows': rows,
        'total_qty': sum(r['quantity'] for r in rows),
        'total_reserved': sum(r['reserved'] for r in rows),
        'illiquid': sum(1 for r in rows if r['illiquid']),
    }
