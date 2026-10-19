from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone
from django.utils.dateformat import format as date_format

from panel.i18n import translate

register = template.Library()


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return key
    if isinstance(mapping, dict):
        return mapping.get(key, key)
    return key


@register.simple_tag(takes_context=True)
def udate(context, value):
    """Дата в формате из настроек пользователя."""
    if not value:
        return '—'
    settings = context.get('panel_settings')
    fmt = settings.date_format if settings else 'd.m.Y H:i'
    if hasattr(value, 'tzinfo') and value.tzinfo is not None:
        value = timezone.localtime(value)
    return date_format(value, fmt)


@register.simple_tag(takes_context=True)
def money(context, value):
    """Сумма в формате валюты из настроек пользователя."""
    if value in (None, ''):
        return '—'
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError):
        return value
    settings = context.get('panel_settings')
    if settings and settings.currency_format == 'rub_code':
        return f'RUB {value:,.2f}'
    text = f'{value:,.2f}'.replace(',', ' ').replace('.', ',')
    return f'{text} ₽'


@register.simple_tag(takes_context=True)
def tr(context, text):
    settings = context.get('panel_settings')
    return translate(text, settings.language if settings else 'ru')


@register.simple_tag(takes_context=True)
def can(context, resource, action):
    from users.permissions import has_permission

    user = context.get('panel_user')
    return bool(user) and has_permission(user.user_role, resource, action)


@register.simple_tag(takes_context=True)
def sort_header(context, key, label):
    """Заголовок колонки с многостолбцовой сортировкой (Shift+клик добавляет колонку)."""
    from django.utils.html import format_html

    keys = context.get('sort_keys') or []
    state = ''
    for i, k in enumerate(keys):
        if k.lstrip('-') == key:
            arrow = '↓' if k.startswith('-') else '↑'
            state = f' {arrow}{i + 1 if len(keys) > 1 else ""}'
    return format_html('<a href="#" class="sort-link" data-sort="{}">{}{}</a>', key, label, state)


@register.filter
def json_pretty(value):
    import json

    if value in (None, ''):
        return ''
    try:
        data = json.loads(value) if isinstance(value, str) else value
        return json.dumps(data, ensure_ascii=False, indent=1)
    except (TypeError, ValueError):
        return value
