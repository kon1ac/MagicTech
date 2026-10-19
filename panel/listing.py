"""Общие механики списков панели: многостолбцовая сортировка, пагинация по настройкам
пользователя, сохранённые и дефолтные фильтры."""

from __future__ import annotations

from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.shortcuts import redirect

from users.models import SavedFilter, UserSettings

FILTER_IGNORED = {'page', 'per_page'}


def apply_sorting(request, qs, allowed: dict[str, str], default: str):
    """?sort=status,-created — несколько колонок через запятую; ключи берутся только из allowed."""
    for raw in (request.GET.get('sort') or default, default):
        order, keys, seen = [], [], set()
        for part in raw.split(','):
            part = part.strip()
            key = part.lstrip('-')
            if key in allowed and key not in seen:
                seen.add(key)
                order.append(('-' if part.startswith('-') else '') + allowed[key])
                keys.append(part)
        if order:
            return qs.order_by(*order), keys
    return qs, []


def paginate(request, qs, user=None, per_page: int | None = None):
    size = per_page
    if size is None:
        try:
            size = int(request.GET.get('per_page') or 0)
        except ValueError:
            size = 0
        if size not in (10, 25, 50, 100):
            size = UserSettings.for_user(user).page_size if user else 25
    return Paginator(qs, size).get_page(request.GET.get('page'))


def default_filter_redirect(request, user, section: str):
    """Если пользователь открыл список без параметров — применяем его дефолтный фильтр."""
    if request.GET or request.method != 'GET':
        return None
    defaults = (UserSettings.for_user(user).default_filters or {}).get(section)
    if defaults:
        return redirect(f'{request.path}?{defaults}')
    return None


def list_context(request, user, section: str, sort_keys=None) -> dict:
    params = request.GET.copy()
    for key in FILTER_IGNORED:
        params.pop(key, None)
    return {
        'section': section,
        'saved_filters': SavedFilter.objects.filter(id_user=user, filter_section=section),
        'current_query': params.urlencode(),
        'sort_keys': sort_keys or [],
        'sort_param': ','.join(sort_keys or []),
        'query_without_page': params.urlencode(),
    }


def build_query(**kwargs) -> str:
    return urlencode({k: v for k, v in kwargs.items() if v not in (None, '')})
