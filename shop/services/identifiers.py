"""Генерация артикулов (SKU) и штрихкодов (EAN/GTIN) для каталога."""

from __future__ import annotations

import re
import secrets
import string

from shop.models import Brand, Category, Product

# Префиксы как в seed_magtech / catalog_2026
SKU_PREFIX_BY_SLUG = {
    'keyboards-mech': 'KB',
    'keyboards-membrane': 'KB',
    'keyboards': 'KB',
    'mice-gaming': 'MS',
    'mice-office': 'MS',
    'mice': 'MS',
    'mousepads': 'MP',
    'headsets': 'HS',
    'webcams': 'WC',
    'usb-hubs': 'HB',
    'cables': 'CB',
    'laptop-stands': 'LS',
    'cable-organizers': 'CO',
    'chairs': 'CH',
    'cooling': 'CL',
    'thermal-paste': 'TP',
    'wipes': 'WP',
    'antistatic': 'AS',
}

_BRAND_OVERRIDES = {
    'KEYCHRON': 'KEY',
    'RAZER': 'RAZ',
    'HYPERX': 'HYP',
    'STEELSERIES': 'STE',
    'LOGITECH': 'LOG',
    'A4TECH': 'A4T',
    'XIAOMI': 'XIA',
    'UGREEN': 'UGR',
    'BASEUS': 'BAS',
    'DXRACER': 'DXR',
    'NOCTUA': 'NOC',
    'ARCTIC': 'ARC',
    'DEFENDER': 'DEF',
    'SONY': 'SONY',
}


def gtin_check_digit(body: str) -> str:
    """Контрольная цифра GTIN/EAN/UPC (Mod-10, веса 3/1 справа налево)."""
    total = 0
    for i, ch in enumerate(reversed(body)):
        total += int(ch) * (3 if i % 2 == 0 else 1)
    return str((10 - (total % 10)) % 10)


def is_valid_gtin(code: str) -> bool:
    if not code or not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    return gtin_check_digit(code[:-1]) == code[-1]


def _brand_code(brand: Brand | None) -> str:
    if not brand or not brand.brand_name:
        return 'GEN'
    raw = re.sub(r'[^A-Za-z0-9]', '', brand.brand_name).upper()
    if not raw:
        return 'GEN'
    if raw in _BRAND_OVERRIDES:
        return _BRAND_OVERRIDES[raw]
    for key, code in _BRAND_OVERRIDES.items():
        if raw.startswith(key):
            return code
    return raw[:3]


def _category_prefix(category: Category | None) -> str:
    node = category
    seen: set[int] = set()
    while node is not None and node.pk not in seen:
        seen.add(node.pk)
        slug = (node.category_slug or '').strip().lower()
        if slug in SKU_PREFIX_BY_SLUG:
            return SKU_PREFIX_BY_SLUG[slug]
        node = node.id_parent
    if category and category.category_slug:
        letters = re.sub(r'[^A-Za-z]', '', category.category_slug).upper()
        if len(letters) >= 2:
            return letters[:2]
    return 'MT'


def _random_suffix(length: int = 5) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_sku(*, category: Category | None = None, brand: Brand | None = None,
                 exclude_pk: int | None = None) -> str:
    """Артикул вида PREFIX-BRAND-XXXXX, уникальный в products.product_sku."""
    prefix = _category_prefix(category)
    mid = _brand_code(brand)
    qs = Product.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    for _ in range(40):
        sku = f'{prefix}-{mid}-{_random_suffix(5)}'
        if len(sku) > 100:
            sku = sku[:100]
        if not qs.filter(product_sku=sku).exists():
            return sku
    raise RuntimeError('Не удалось сгенерировать уникальный артикул.')


def generate_ean13(*, exclude_pk: int | None = None) -> str:
    """EAN-13 с валидной контрольной цифрой. Префикс 200 — внутренний (магазинный) код."""
    qs = Product.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    for _ in range(40):
        body = '200' + f'{secrets.randbelow(10**9):09d}'
        code = body + gtin_check_digit(body)
        if not qs.filter(product_ean=code).exists():
            return code
    raise RuntimeError('Не удалось сгенерировать уникальный EAN.')
