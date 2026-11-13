"""Серверный поиск и фильтрация каталога, динамические фасеты, кеширование справочников."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import BooleanField, Count, F, FloatField, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.expressions import RawSQL
from django.db.models.functions import Coalesce

from shop.models import Brand, Category, Characteristic, OrderItem, Product, Stock
from shop.services.pricing import current_price_subquery

SORTS = {
    'popular': ('-sales_count', '-id_product'),
    'new': ('-created_at', '-id_product'),
    'price_asc': (F('price_now').asc(nulls_last=True), 'id_product'),
    'price_desc': (F('price_now').desc(nulls_last=True), 'id_product'),
    'rating': ('-rating_avg', '-rating_count', '-id_product'),
}
SORT_LABELS = {
    'popular': 'По популярности',
    'new': 'Новинки',
    'price_asc': 'Сначала дешёвые',
    'price_desc': 'Сначала дорогие',
    'rating': 'По рейтингу',
}


def is_postgres() -> bool:
    return connection.vendor == 'postgresql'


def available_subquery():
    return Coalesce(
        Subquery(
            Stock.objects.filter(id_product=OuterRef('pk'))
            .annotate(av=F('stock_quantity') - F('stock_reserved'))
            .values('av')[:1],
            output_field=IntegerField(),
        ),
        Value(0),
    )


def base_queryset():
    return (
        Product.objects.filter(is_active=True)
        .select_related('id_brand', 'id_category')
        .prefetch_related('media')
        .annotate(price_now=current_price_subquery(), available=available_subquery())
    )


def category_tree():
    """Дерево категорий до 3 уровней (кешируется)."""
    key = 'catalog:category_tree'
    tree = cache.get(key)
    if tree is None:
        nodes = list(Category.objects.filter(is_active=True).order_by('category_name').values(
            'id_category', 'id_parent', 'category_name', 'category_slug', 'category_level'))
        children = defaultdict(list)
        for node in nodes:
            children[node['id_parent']].append(node)

        def build(parent_id, depth):
            if depth > 3:
                return []
            return [dict(node, children=build(node['id_category'], depth + 1)) for node in children[parent_id]]

        tree = build(None, 1)
        cache.set(key, tree, settings.MAGTECH_CATALOG_CACHE_TTL)
    return tree


def invalidate_catalog_cache():
    cache.delete('catalog:category_tree')
    cache.delete('catalog:filterable')
    version = cache.get('catalog:facet_version', 0) + 1
    cache.set('catalog:facet_version', version, None)


def filterable_characteristics():
    key = 'catalog:filterable'
    data = cache.get(key)
    if data is None:
        data = {c.char_code: c.char_name for c in Characteristic.objects.filter(is_filterable=True)}
        cache.set(key, data, settings.MAGTECH_CATALOG_CACHE_TTL)
    return data


def apply_search(qs, q: str):
    q = (q or '').strip()[:200]
    if not q:
        return qs, False
    if is_postgres():
        # полнотекстовый поиск с морфологией (словарь russian) по генерируемой колонке + GIN
        match = RawSQL(
            "products.search_vector @@ websearch_to_tsquery('russian', %s)", (q,), output_field=BooleanField()
        )
        rank = RawSQL("ts_rank(products.search_vector, websearch_to_tsquery('russian', %s))", (q,), output_field=FloatField())
        qs = qs.annotate(fts_match=match, search_rank=rank).filter(
            Q(fts_match=True) | Q(product_sku__iexact=q) | Q(id_brand__brand_name__iexact=q)
        )
        return qs, True
    flt = Q()
    for word in q.split():
        flt &= (
            Q(product_name__icontains=word) | Q(product_sku__icontains=word)
            | Q(product_description__icontains=word) | Q(id_brand__brand_name__icontains=word)
        )
    return qs.filter(flt), False


def parse_filters(params) -> dict:
    def decimal_or_none(value):
        try:
            return Decimal(value) if value not in (None, '') else None
        except InvalidOperation:
            return None

    chars = {}
    for code in filterable_characteristics():
        values = [v for v in params.getlist(f'f_{code}') if v]
        if values:
            chars[code] = values[:20]
    brands = [b for b in params.getlist('brand') if b.isdigit()][:50]
    return {
        'q': (params.get('q') or '').strip(),
        'category': params.get('category') or '',
        'brands': brands,
        'price_min': decimal_or_none(params.get('price_min')),
        'price_max': decimal_or_none(params.get('price_max')),
        'in_stock': params.get('in_stock') == '1',
        'chars': chars,
        'sort': params.get('sort') if params.get('sort') in SORTS else 'popular',
    }


def search(filters: dict):
    """Возвращает (queryset, category, facets). Все фильтры — на стороне сервера/СУБД."""
    qs = base_queryset()
    category = None
    if filters['category']:
        category = Category.objects.filter(category_slug=filters['category'], is_active=True).first()
        if category:
            qs = qs.filter(id_category__in=category.descendant_ids())
    qs, ranked = apply_search(qs, filters['q'])
    scope = qs  # область для фасетов: категория + поиск

    if filters['brands']:
        qs = qs.filter(id_brand__in=filters['brands'])
    if filters['price_min'] is not None:
        qs = qs.filter(price_now__gte=filters['price_min'])
    if filters['price_max'] is not None:
        qs = qs.filter(price_now__lte=filters['price_max'])
    if filters['in_stock']:
        qs = qs.filter(available__gt=0)
    for code, values in filters['chars'].items():
        flt = Q()
        for value in values:
            flt |= Q(**{f'product_characteristics__{code}': value})
        qs = qs.filter(flt)

    order = SORTS[filters['sort']]
    if ranked and filters['sort'] == 'popular':
        order = ('-search_rank',) + order
    qs = qs.order_by(*order)
    return qs, category, facets(scope, filters)


def facets(scope, filters) -> dict:
    """Динамические фильтры: показываются только значения, реально встречающиеся в выборке."""
    raw = None
    if is_postgres():
        try:
            raw = scope.values('pk').query.sql_with_params()
        except Exception:
            # пустая выборка (например, несуществующая категория) → фасеты пустые
            raw = None
    key_src = f"{filters['category']}|{filters['q']}|{cache.get('catalog:facet_version', 0)}"
    key = 'catalog:facets:' + hashlib.md5(key_src.encode()).hexdigest()
    data = cache.get(key)
    if data is not None:
        return data
    names = filterable_characteristics()
    brand_rows = (
        scope.order_by().values('id_brand', 'id_brand__brand_name')
        .annotate(cnt=Count('pk')).filter(id_brand__isnull=False).order_by('id_brand__brand_name')
    )
    chars = defaultdict(dict)
    if raw:
        # {sql} — SQL, сгенерированный Django ORM (sql_with_params), а не строка
        # из запроса пользователя; значения по-прежнему уходят плейсхолдерами %s.
        # Подзапрос держим внутри СУБД: вытаскивать id товаров в Python и
        # разворачивать их в IN (…) нельзя — на каталоге в десятки тысяч
        # позиций запрос деградирует и упирается в лимиты параметров.
        sql, params = raw
        with connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT kv.key, kv.value, COUNT(*) FROM products p
                    CROSS JOIN LATERAL jsonb_each_text(p.product_characteristics) kv
                    WHERE p.id_product IN ({sql}) AND kv.key = ANY(%s)
                    GROUP BY kv.key, kv.value ORDER BY kv.key, kv.value""",
                [*params, list(names)],
            )
            for code, value, cnt in cursor.fetchall():
                chars[code][value] = cnt
    else:
        for row in scope.order_by().values_list('product_characteristics', flat=True)[:5000]:
            for code, value in (row or {}).items():
                if code in names:
                    chars[code][str(value)] = chars[code].get(str(value), 0) + 1
    data = {
        'brands': [{'id': r['id_brand'], 'name': r['id_brand__brand_name'], 'count': r['cnt']} for r in brand_rows],
        'chars': [
            {'code': code, 'name': names[code], 'values': sorted(values.items())}
            for code, values in chars.items() if values
        ],
    }
    cache.set(key, data, settings.MAGTECH_CATALOG_CACHE_TTL)
    return data


def also_bought(product: Product, limit: int = 6):
    """«С этим также покупают» — товары из тех же заказов, по частоте совместных покупок."""
    order_ids = OrderItem.objects.filter(id_product=product).values('id_order')
    ids = list(
        OrderItem.objects.filter(id_order__in=order_ids).exclude(id_product=product)
        .values('id_product').annotate(cnt=Count('id_order')).order_by('-cnt')
        .values_list('id_product', flat=True)[:limit]
    )
    qs = base_queryset().filter(pk__in=ids)
    if len(ids) < limit and product.id_category_id:
        extra = base_queryset().filter(id_category=product.id_category).exclude(pk=product.pk).exclude(
            pk__in=ids).order_by('-sales_count')[: limit - len(ids)]
        return list(qs) + list(extra)
    return list(qs)


def brands_cached():
    key = 'catalog:brands'
    data = cache.get(key)
    if data is None:
        data = list(Brand.objects.filter(is_active=True).order_by('brand_name').values('id_brand', 'brand_name'))
        cache.set(key, data, settings.MAGTECH_CATALOG_CACHE_TTL)
    return data


def _query_without(params, *, drop_keys=None, drop_values=None) -> str:
    """Собирает querystring без указанных ключей/значений (для чипов сброса)."""
    from urllib.parse import urlencode

    drop_keys = set(drop_keys or ())
    drop_values = drop_values or {}  # {key: set(values)}
    pairs = []
    for key in params.keys():
        if key in drop_keys or key == 'page':
            continue
        banned = set(drop_values.get(key, ()))
        for val in params.getlist(key):
            if val in banned or val in ('', None):
                continue
            pairs.append((key, val))
    return urlencode(pairs)


def active_filter_chips(filters: dict, params, *, category=None, facets_data=None) -> list[dict]:
    """Чипы активных фильтров: label + href без этого фильтра."""
    facets_data = facets_data or {}
    brand_names = {str(b['id']): b['name'] for b in facets_data.get('brands', [])}
    if not brand_names and filters.get('brands'):
        for row in Brand.objects.filter(pk__in=filters['brands']).values('id_brand', 'brand_name'):
            brand_names[str(row['id_brand'])] = row['brand_name']
    char_names = filterable_characteristics()
    chips = []

    if filters.get('q'):
        qs = _query_without(params, drop_keys={'q'})
        chips.append({'key': 'q', 'label': f'Поиск: «{filters["q"]}»', 'href': qs})
    if filters.get('in_stock'):
        chips.append({
            'key': 'in_stock', 'label': 'В наличии',
            'href': _query_without(params, drop_keys={'in_stock'}),
        })
    if filters.get('price_min') is not None:
        chips.append({
            'key': 'price_min', 'label': f'от {int(filters["price_min"])} ₽',
            'href': _query_without(params, drop_keys={'price_min'}),
        })
    if filters.get('price_max') is not None:
        chips.append({
            'key': 'price_max', 'label': f'до {int(filters["price_max"])} ₽',
            'href': _query_without(params, drop_keys={'price_max'}),
        })
    for bid in filters.get('brands') or []:
        chips.append({
            'key': f'brand:{bid}',
            'label': brand_names.get(str(bid), f'Бренд #{bid}'),
            'href': _query_without(params, drop_values={'brand': {str(bid)}}),
        })
    for code, values in (filters.get('chars') or {}).items():
        title = char_names.get(code, code)
        for value in values:
            chips.append({
                'key': f'f_{code}:{value}',
                'label': f'{title}: {value}',
                'href': _query_without(params, drop_values={f'f_{code}': {value}}),
            })
    # сортировка не-дефолтная — тоже чип
    if filters.get('sort') and filters['sort'] != 'popular':
        chips.append({
            'key': 'sort',
            'label': SORT_LABELS.get(filters['sort'], filters['sort']),
            'href': _query_without(params, drop_keys={'sort'}),
        })
    return chips


def suggest_search(q: str, limit: int = 8) -> dict:
    """Подсказки поиска: товары, бренды, «возможно, вы имели в виду»."""
    import difflib
    from urllib.parse import quote

    q = (q or '').strip()[:80]
    if len(q) < 1:
        return {'products': [], 'brands': [], 'did_you_mean': None}

    q_lower = q.lower()
    products_out = []
    qs = base_queryset()

    # точный SKU / префикс артикула
    sku_hits = list(qs.filter(product_sku__istartswith=q).order_by('product_sku')[:3])
    # название / бренд
    name_hits = list(
        qs.filter(
            Q(product_name__icontains=q) | Q(id_brand__brand_name__icontains=q)
        ).exclude(pk__in=[p.pk for p in sku_hits]).order_by('-sales_count')[: limit]
    )
    seen = set()
    for p in sku_hits + name_hits:
        if p.pk in seen:
            continue
        seen.add(p.pk)
        products_out.append({
            'sku': p.product_sku,
            'name': p.product_name,
            'brand': p.id_brand.brand_name if p.id_brand_id else '',
            'price': float(p.price_now) if p.price_now is not None else None,
            'image': p.main_image or '',
            'url': f'/product/{p.product_sku}/',
        })
        if len(products_out) >= limit:
            break

    brands_out = []
    for row in brands_cached():
        name = row['brand_name']
        if q_lower in name.lower():
            brands_out.append({
                'name': name,
                'url': f'/?q={quote(name)}',
            })
        if len(brands_out) >= 5:
            break

    did_you_mean = None
    if not products_out and not brands_out and len(q) >= 3:
        brand_names = [r['brand_name'] for r in brands_cached()]
        brand_map = {n.lower(): n for n in brand_names}
        close = difflib.get_close_matches(q_lower, list(brand_map.keys()), n=1, cutoff=0.55)
        if close:
            did_you_mean = brand_map[close[0]]
            fixed = list(
                qs.filter(id_brand__brand_name__iexact=did_you_mean).order_by('-sales_count')[:limit]
            )
            for p in fixed:
                products_out.append({
                    'sku': p.product_sku,
                    'name': p.product_name,
                    'brand': p.id_brand.brand_name if p.id_brand_id else '',
                    'price': float(p.price_now) if p.price_now is not None else None,
                    'image': p.main_image or '',
                    'url': f'/product/{p.product_sku}/',
                })
            brands_out.append({'name': did_you_mean, 'url': f'/?q={quote(did_you_mean)}'})
        else:
            names = list(
                Product.objects.filter(is_active=True)
                .order_by('-sales_count')
                .values_list('product_name', flat=True)[:300]
            )
            name_map = {n.lower(): n for n in names if n}
            close_n = difflib.get_close_matches(q_lower, list(name_map.keys()), n=1, cutoff=0.5)
            if close_n:
                did_you_mean = name_map[close_n[0]]
                for p in qs.filter(product_name=did_you_mean)[:limit]:
                    products_out.append({
                        'sku': p.product_sku,
                        'name': p.product_name,
                        'brand': p.id_brand.brand_name if p.id_brand_id else '',
                        'price': float(p.price_now) if p.price_now is not None else None,
                        'image': p.main_image or '',
                        'url': f'/product/{p.product_sku}/',
                    })

    return {
        'products': products_out,
        'brands': brands_out,
        'did_you_mean': did_you_mean,
        'q': q,
    }
