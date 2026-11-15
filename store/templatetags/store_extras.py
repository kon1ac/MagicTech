"""Хелперы витрины: остаток и бейджи совместимости."""

from django import template

register = template.Library()

# Показываем число только когда остаток действительно мал.
LOW_STOCK_THRESHOLD = 5


@register.filter
def stock_state(available):
    """Возвращает dict: kind (ok|low|out), text."""
    try:
        qty = int(available)
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        return {'kind': 'out', 'text': 'Нет в наличии', 'qty': 0}
    if qty <= LOW_STOCK_THRESHOLD:
        unit = 'шт.'
        return {'kind': 'low', 'text': f'Осталось {qty} {unit}', 'qty': qty}
    return {'kind': 'ok', 'text': 'В наличии', 'qty': qty}


@register.filter
def compat_badges(product_or_chars):
    """Бейджи Win / macOS / Bluetooth / USB из характеристик товара.

    Читает product.product_characteristics или готовый dict.
    Не выдумывает ОС, если в подключении нет USB/Bluetooth/2.4.
    """
    if product_or_chars is None:
        return []
    chars = product_or_chars
    if hasattr(product_or_chars, 'product_characteristics'):
        chars = product_or_chars.product_characteristics or {}
    if not isinstance(chars, dict):
        return []

    badges = []
    seen = set()

    def add(key, label):
        if key in seen:
            return
        seen.add(key)
        badges.append({'key': key, 'label': label})

    os_raw = str(chars.get('os') or chars.get('platform') or chars.get('compatibility') or '')
    os_l = os_raw.lower()
    if os_l:
        if 'win' in os_l or 'windows' in os_l:
            add('win', 'Windows')
        if 'mac' in os_l or 'os x' in os_l or 'osx' in os_l:
            add('mac', 'macOS')
        if 'linux' in os_l:
            add('linux', 'Linux')

    conn = str(chars.get('connection') or '').lower()
    wirelessish = any(x in conn for x in ('bluetooth', '2.4', 'wireless', 'беспровод'))
    wired_usb = 'usb' in conn

    if not os_raw and (wirelessish or wired_usb):
        # HID/периферия с USB или радио обычно работает на Win и macOS
        add('win', 'Windows')
        add('mac', 'macOS')

    if 'bluetooth' in conn:
        bt_label = 'Bluetooth'
        for token in ('5.3', '5.2', '5.1', '5.0', '5.x', '4.2', '4.0'):
            if token in conn:
                bt_label = f'Bluetooth {token}'
                break
        add('bt', bt_label)
    if '2.4' in conn:
        add('radio', '2.4 ГГц')
    if wired_usb:
        if 'usb-c' in conn or 'type-c' in conn:
            add('usbc', 'USB-C')
        elif 'bluetooth' not in conn:
            add('usb', 'USB')

    return badges


COLOR_MAP = {
    'чёрный': '#1a1d23', 'черный': '#1a1d23', 'black': '#1a1d23',
    'белый': '#f4f6f8', 'белыйй': '#f4f6f8', 'white': '#f4f6f8',
    'серый': '#8b93a0', 'gray': '#8b93a0', 'grey': '#8b93a0',
    'серебристый': '#c5cad3', 'silver': '#c5cad3',
    'красный': '#c23b3b', 'red': '#c23b3b',
    'синий': '#2563eb', 'blue': '#2563eb',
    'зелёный': '#2f7d55', 'зеленый': '#2f7d55', 'green': '#2f7d55',
    'розовый': '#e879a9', 'pink': '#e879a9',
    'фиолетовый': '#7c3aed', 'purple': '#7c3aed',
    'оранжевый': '#d97706', 'orange': '#d97706',
    'жёлтый': '#eab308', 'желтый': '#eab308', 'yellow': '#eab308',
    'коричневый': '#92400e', 'brown': '#92400e',
    'бирюзовый': '#0d9488', 'cyan': '#0d9488',
}


@register.filter
def color_swatch(product_or_chars):
    """Один кружок цвета из характеристики color, либо None."""
    chars = product_or_chars
    if hasattr(product_or_chars, 'product_characteristics'):
        chars = product_or_chars.product_characteristics or {}
    if not isinstance(chars, dict):
        return None
    raw = str(chars.get('color') or '').strip()
    if not raw:
        return None
    key = raw.lower()
    hex_color = COLOR_MAP.get(key)
    if not hex_color:
        for name, value in COLOR_MAP.items():
            if name in key:
                hex_color = value
                break
    if not hex_color:
        hex_color = '#8b93a0'
    return {'label': raw, 'hex': hex_color}


@register.filter
def char_value(product, code):
    chars = getattr(product, 'product_characteristics', None) or {}
    if not isinstance(chars, dict):
        return '—'
    val = chars.get(code)
    return val if val not in (None, '') else '—'
