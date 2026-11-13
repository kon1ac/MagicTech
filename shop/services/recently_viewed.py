"""Недавно просмотренные товары — в сессии браузера."""

from __future__ import annotations

SESSION_KEY = 'recently_viewed'
MAX_ITEMS = 12


def track(request, sku: str) -> None:
    sku = (sku or '').strip()
    if not sku:
        return
    items = [s for s in request.session.get(SESSION_KEY, []) if s != sku]
    items.insert(0, sku)
    request.session[SESSION_KEY] = items[:MAX_ITEMS]
    request.session.modified = True


def skus(request, exclude: str | None = None, limit: int = 8) -> list[str]:
    items = list(request.session.get(SESSION_KEY, []))
    if exclude:
        items = [s for s in items if s != exclude]
    return items[:limit]


def products(request, exclude: str | None = None, limit: int = 8):
    from shop.services.catalog import base_queryset

    codes = skus(request, exclude=exclude, limit=limit)
    if not codes:
        return []
    found = {
        p.product_sku: p
        for p in base_queryset().filter(product_sku__in=codes).prefetch_related('media')
    }
    return [found[s] for s in codes if s in found]
