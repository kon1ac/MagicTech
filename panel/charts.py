"""Данные для сводных Chart.js-графиков на страницах панели + период."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

PERIODS = {
    '7d': (7, '7 дней'),
    '30d': (30, '30 дней'),
    '90d': (90, '90 дней'),
}


def parse_period(request) -> tuple[str, int, str]:
    key = request.GET.get('chart_period', '30d')
    if key not in PERIODS:
        key = '30d'
    days, label = PERIODS[key]
    return key, days, label


def _since(days: int):
    return timezone.now() - timedelta(days=days)


def products_charts(days: int = 30) -> dict:
    from shop.models import OrderItem, Product, Stock

    since = _since(days)
    sold = list(
        OrderItem.objects.filter(
            id_order__created_at__gte=since,
            id_order__order_status__in=['PAID', 'CONFIRMED', 'ASSEMBLY', 'PACKED', 'COMPLETED'],
        )
        .values('id_product__product_name', 'id_product__product_sku')
        .annotate(qty=Sum('order_item_quantity'))
        .order_by('-qty')[:10]
    )
    active = Product.objects.filter(is_active=True).count()
    inactive = Product.objects.filter(is_active=False).count()
    stock_rows = list(
        Stock.objects.select_related('id_product')
        .annotate(avail=F('stock_quantity') - F('stock_reserved'))
        .order_by('avail')[:10]
    )
    created = list(
        Product.objects.filter(created_at__gte=since)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(cnt=Count('id_product'))
        .order_by('day')
    )
    return {
        'charts': [
            {
                'id': 'chPopular',
                'title': f'Топ продаж ({days} дн.)',
                'type': 'bar',
                'horizontal': True,
                'labels': [r['id_product__product_name'][:28] for r in sold] or ['нет данных'],
                'datasets': [{'label': 'шт.', 'data': [int(r['qty'] or 0) for r in sold] or [0]}],
            },
            {
                'id': 'chActive',
                'title': 'Активность каталога',
                'type': 'doughnut',
                'labels': ['В продаже', 'Сняты'],
                'datasets': [{'data': [active, inactive]}],
            },
            {
                'id': 'chLowStock',
                'title': 'Наименьшие остатки',
                'type': 'bar',
                'labels': [s.id_product.product_sku for s in stock_rows] or ['—'],
                'datasets': [{'label': 'доступно', 'data': [s.available_quantity for s in stock_rows] or [0]}],
            },
            {
                'id': 'chNew',
                'title': f'Новые товары ({days} дн.)',
                'type': 'line',
                'labels': [str(r['day']) for r in created] or ['—'],
                'datasets': [{'label': 'создано', 'data': [r['cnt'] for r in created] or [0], 'fill': True}],
            },
        ],
    }


def categories_charts(days: int = 30) -> dict:
    from shop.models import Category, OrderItem, Product

    since = _since(days)
    by_level = list(
        Category.objects.values('category_level').annotate(cnt=Count('id_category')).order_by('category_level')
    )
    products_per = list(
        Product.objects.filter(is_active=True, id_category__isnull=False)
        .values('id_category__category_name')
        .annotate(cnt=Count('id_product'))
        .order_by('-cnt')[:10]
    )
    sales = list(
        OrderItem.objects.filter(
            id_order__created_at__gte=since,
            id_order__order_status__in=['PAID', 'CONFIRMED', 'ASSEMBLY', 'PACKED', 'COMPLETED'],
        )
        .values('id_product__id_category__category_name')
        .annotate(qty=Sum('order_item_quantity'))
        .order_by('-qty')[:8]
    )
    active = Category.objects.filter(is_active=True).count()
    inactive = Category.objects.filter(is_active=False).count()
    return {
        'charts': [
            {
                'id': 'chCatLevel',
                'title': 'Категории по уровням',
                'type': 'bar',
                'labels': [f'Ур. {r["category_level"]}' for r in by_level] or ['—'],
                'datasets': [{'label': 'шт.', 'data': [r['cnt'] for r in by_level] or [0]}],
            },
            {
                'id': 'chCatProducts',
                'title': 'Товаров в категории',
                'type': 'doughnut',
                'labels': [r['id_category__category_name'][:22] for r in products_per] or ['—'],
                'datasets': [{'data': [r['cnt'] for r in products_per] or [0]}],
            },
            {
                'id': 'chCatSales',
                'title': f'Продажи по категориям ({days} дн.)',
                'type': 'bar',
                'horizontal': True,
                'labels': [(r['id_product__id_category__category_name'] or 'без кат.')[:22] for r in sales] or ['—'],
                'datasets': [{'label': 'шт.', 'data': [int(r['qty'] or 0) for r in sales] or [0]}],
            },
            {
                'id': 'chCatActive',
                'title': 'Активность категорий',
                'type': 'doughnut',
                'labels': ['Активны', 'Выкл.'],
                'datasets': [{'data': [active, inactive]}],
            },
        ],
    }


def brands_charts(days: int = 30) -> dict:
    from shop.models import Brand, OrderItem, Product

    since = _since(days)
    products_per = list(
        Product.objects.filter(is_active=True, id_brand__isnull=False)
        .values('id_brand__brand_name')
        .annotate(cnt=Count('id_product'))
        .order_by('-cnt')[:10]
    )
    sales = list(
        OrderItem.objects.filter(
            id_order__created_at__gte=since,
            id_order__order_status__in=['PAID', 'CONFIRMED', 'ASSEMBLY', 'PACKED', 'COMPLETED'],
        )
        .values('id_product__id_brand__brand_name')
        .annotate(qty=Sum('order_item_quantity'), revenue=Sum('order_item_total'))
        .order_by('-qty')[:8]
    )
    active = Brand.objects.filter(is_active=True).count()
    inactive = Brand.objects.filter(is_active=False).count()
    return {
        'charts': [
            {
                'id': 'chBrandProducts',
                'title': 'SKU по брендам',
                'type': 'bar',
                'labels': [r['id_brand__brand_name'][:20] for r in products_per] or ['—'],
                'datasets': [{'label': 'товаров', 'data': [r['cnt'] for r in products_per] or [0]}],
            },
            {
                'id': 'chBrandSales',
                'title': f'Популярность бренда ({days} дн.)',
                'type': 'bar',
                'horizontal': True,
                'labels': [(r['id_product__id_brand__brand_name'] or '—')[:20] for r in sales] or ['—'],
                'datasets': [{'label': 'продано шт.', 'data': [int(r['qty'] or 0) for r in sales] or [0]}],
            },
            {
                'id': 'chBrandRev',
                'title': f'Выручка по брендам ({days} дн.)',
                'type': 'doughnut',
                'labels': [(r['id_product__id_brand__brand_name'] or '—')[:18] for r in sales] or ['—'],
                'datasets': [{'data': [float(r['revenue'] or 0) for r in sales] or [0]}],
            },
            {
                'id': 'chBrandActive',
                'title': 'Активность брендов',
                'type': 'doughnut',
                'labels': ['Активны', 'Выкл.'],
                'datasets': [{'data': [active, inactive]}],
            },
        ],
    }


def characteristics_charts(days: int = 30) -> dict:
    from shop.models import Characteristic, Product

    by_type = list(
        Characteristic.objects.values('char_value_type').annotate(cnt=Count('id_characteristic')).order_by('-cnt')
    )
    filterable = Characteristic.objects.filter(is_filterable=True).count()
    plain = Characteristic.objects.filter(is_filterable=False).count()
    # сколько товаров имеют ключ характеристики в JSON — приближённо по кодам
    codes = list(Characteristic.objects.order_by('sort_order').values_list('char_code', 'char_name')[:12])
    usage = []
    products = list(Product.objects.filter(is_active=True).values_list('product_characteristics', flat=True)[:2000])
    for code, name in codes:
        usage.append({'name': name, 'cnt': sum(1 for ch in products if isinstance(ch, dict) and code in ch)})
    usage.sort(key=lambda r: -r['cnt'])
    return {
        'charts': [
            {
                'id': 'chCharType',
                'title': 'По типу значения',
                'type': 'doughnut',
                'labels': [r['char_value_type'] for r in by_type] or ['—'],
                'datasets': [{'data': [r['cnt'] for r in by_type] or [0]}],
            },
            {
                'id': 'chCharFilter',
                'title': 'В фильтрах каталога',
                'type': 'doughnut',
                'labels': ['В фильтрах', 'Только карточка'],
                'datasets': [{'data': [filterable, plain]}],
            },
            {
                'id': 'chCharUsage',
                'title': 'Заполненность у товаров',
                'type': 'bar',
                'horizontal': True,
                'labels': [r['name'][:22] for r in usage[:8]] or ['—'],
                'datasets': [{'label': 'товаров', 'data': [r['cnt'] for r in usage[:8]] or [0]}],
            },
        ],
    }


def promotions_charts(days: int = 30) -> dict:
    from shop.models import OrderPromotion, Promotion

    now = timezone.now()
    since = _since(days)
    active = Promotion.objects.filter(is_active=True, start_at__lte=now).filter(
        models_q_end(now)
    ).count()
    scheduled = Promotion.objects.filter(is_active=True, start_at__gt=now).count()
    ended = Promotion.objects.filter(end_at__lt=now).count()
    by_type = list(Promotion.objects.values('promotion_type').annotate(cnt=Count('id_promotion')))
    top_usage = list(Promotion.objects.order_by('-usage_count')[:8].values('promotion_name', 'usage_count'))
    recent = list(
        OrderPromotion.objects.filter(id_order__created_at__gte=since)
        .values('id_promotion__promotion_name')
        .annotate(cnt=Count('id_order_promotion'))
        .order_by('-cnt')[:8]
    )
    return {
        'charts': [
            {
                'id': 'chPromoStatus',
                'title': 'Статус акций',
                'type': 'doughnut',
                'labels': ['Активны сейчас', 'Запланированы', 'Завершены'],
                'datasets': [{'data': [active, scheduled, ended]}],
            },
            {
                'id': 'chPromoType',
                'title': 'Тип скидки',
                'type': 'doughnut',
                'labels': [r['promotion_type'] for r in by_type] or ['—'],
                'datasets': [{'data': [r['cnt'] for r in by_type] or [0]}],
            },
            {
                'id': 'chPromoUsage',
                'title': 'Использования (всего)',
                'type': 'bar',
                'horizontal': True,
                'labels': [r['promotion_name'][:24] for r in top_usage] or ['—'],
                'datasets': [{'label': 'раз', 'data': [r['usage_count'] for r in top_usage] or [0]}],
            },
            {
                'id': 'chPromoRecent',
                'title': f'Применения за {days} дн.',
                'type': 'bar',
                'labels': [(r['id_promotion__promotion_name'] or '—')[:20] for r in recent] or ['—'],
                'datasets': [{'label': 'заказов', 'data': [r['cnt'] for r in recent] or [0]}],
            },
        ],
    }


def models_q_end(now):
    from django.db.models import Q

    return Q(end_at__isnull=True) | Q(end_at__gte=now)


SECTION_CHARTS = {
    'products': products_charts,
    'categories': categories_charts,
    'brands': brands_charts,
    'characteristics': characteristics_charts,
    'promotions': promotions_charts,
}


def charts_for(section: str, request) -> dict:
    key, days, label = parse_period(request)
    builder = SECTION_CHARTS.get(section)
    if not builder:
        return {'chart_period': key, 'chart_period_label': label, 'chart_periods': PERIODS, 'page_charts': []}
    data = builder(days)
    return {
        'chart_period': key,
        'chart_period_label': label,
        'chart_periods': PERIODS,
        'page_charts': data['charts'],
        'page_charts_json': data['charts'],
    }
