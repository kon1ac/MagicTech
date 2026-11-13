"""Smoke-обход панели под DB_ADMIN через live runserver (requests + session)."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import requests

BASE = 'http://127.0.0.1:8000'
EMAIL = 'db@magtech.local'
PASSWORD = 'DbAdmin123!'

GET_PATHS = [
    '/panel/',
    '/panel/reports/',
    '/panel/products/',
    '/panel/products/?chart_period=7d',
    '/panel/products/new/',
    '/panel/categories/',
    '/panel/categories/?chart_period=90d',
    '/panel/categories/new/',
    '/panel/brands/',
    '/panel/brands/?chart_period=30d',
    '/panel/brands/new/',
    '/panel/characteristics/',
    '/panel/characteristics/new/',
    '/panel/promotions/',
    '/panel/promotions/new/',
    '/panel/reviews/',
    '/panel/io/',
    '/panel/orders/',
    '/panel/stock/',
    '/panel/stock/export.csv',
    '/panel/stock/movements/',
    '/panel/stock/receipt/',
    '/panel/picking/',
    '/panel/payments/',
    '/panel/statements/',
    '/panel/returns/',
    '/panel/users/',
    '/panel/users/new/',
    '/panel/users/rbac/',
    '/panel/references/',
    '/panel/db/',
    '/panel/db/schema/',
    '/panel/db/backups/',
    '/panel/db/jobs/',
    '/panel/db/service-accounts/',
    '/panel/archive/',
    '/panel/audit/',
    '/panel/audit/?action=login&q=db',
    '/panel/settings/',
    '/panel/help/hotkeys/',
    '/panel/help/brandbook/',
    '/panel/search/?q=заказ',
]


def csrf(html: str) -> str:
    m = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)', html)
    return m.group(1) if m else ''


def main() -> int:
    s = requests.Session()
    errors: list[tuple] = []

    login_page = s.get(f'{BASE}/panel/login/', timeout=30)
    token = csrf(login_page.text)
    r = s.post(f'{BASE}/panel/login/', data={
        'email': EMAIL, 'password': PASSWORD, 'csrfmiddlewaretoken': token,
    }, headers={'Referer': f'{BASE}/panel/login/'}, timeout=30, allow_redirects=True)
    if '/panel/login' in r.url and 'Неверный' in r.text:
        print('LOGIN FAIL')
        return 1
    print('LOGIN OK', r.url, 'role_ok' if 'Администратор БД' in r.text or 'db@' in r.text else '')

    for path in GET_PATHS:
        resp = s.get(f'{BASE}{path}', timeout=60)
        if resp.status_code >= 400:
            errors.append(('GET', path, resp.status_code))
            print('FAIL', resp.status_code, path)
        else:
            print('OK ', resp.status_code, path)

    # users: ciphertext
    users = s.get(f'{BASE}/panel/users/', timeout=30)
    if 'enc:v1:' not in users.text:
        # may still be ok if no profiles encrypted — warn
        print('WARN users list has no enc:v1: preview')
    else:
        print('OK  PII ciphertext on users list')
    # should not show common seed first names as plain in PII column context — soft check
    if 'Алексей' in users.text and 'enc:v1:' in users.text:
        # email/history might still mention — only fail if appears outside scripts
        print('NOTE plaintext Алексей still somewhere on page (check if in cipher column)')

    # decrypt page GET
    m = re.search(r'/panel/users/(\d+)/decrypt/', users.text)
    if not m:
        m2 = re.search(r'/panel/users/(\d+)/edit/', users.text)
        uid = m2.group(1) if m2 else None
    else:
        uid = m.group(1)
    if uid:
        d = s.get(f'{BASE}/panel/users/{uid}/decrypt/', timeout=30)
        print('OK  decrypt page', d.status_code)
        if d.status_code == 200:
            tok = csrf(d.text)
            d2 = s.post(f'{BASE}/panel/users/{uid}/decrypt/', data={
                'csrfmiddlewaretoken': tok, 'confirm': '1', 'reason': 'smoke test decrypt',
            }, headers={'Referer': f'{BASE}/panel/users/{uid}/decrypt/'}, timeout=30)
            print('OK  decrypt POST', d2.status_code, 'revealed' if 'Расшифрованные' in d2.text or 'Имя' in d2.text else '')

    # create + delete brand
    page = s.get(f'{BASE}/panel/brands/new/', timeout=30)
    tok = csrf(page.text)
    slug = f'smoke-{int(time.time())}'
    r = s.post(f'{BASE}/panel/brands/new/', data={
        'csrfmiddlewaretoken': tok,
        'brand_name': f'Smoke {slug}',
        'brand_slug': slug,
        'brand_description': 'smoke',
        'is_active': 'on',
    }, headers={'Referer': f'{BASE}/panel/brands/new/'}, timeout=30, allow_redirects=True)
    print('POST brand', r.status_code, 'created' if slug in r.text or r.url.endswith('/brands/') else r.url)
    # find brand id
    listing = s.get(f'{BASE}/panel/brands/?q={slug}', timeout=30)
    mid = re.search(rf'/panel/brands/(\d+)/edit/[^"]*{slug}|{slug}.*?/panel/brands/(\d+)/delete/', listing.text, re.S)
    # simpler: look delete link near slug
    mid = re.search(rf'{slug}.*?href="/panel/brands/(\d+)/delete/"', listing.text, re.S)
    if not mid:
        mid = re.search(r'/panel/brands/(\d+)/delete/', listing.text)
    if mid:
        bid = mid.group(1)
        del_page = s.get(f'{BASE}/panel/brands/{bid}/delete/', timeout=30)
        tok = csrf(del_page.text)
        r = s.post(f'{BASE}/panel/brands/{bid}/delete/', data={
            'csrfmiddlewaretoken': tok, 'confirm': '1',
        }, headers={'Referer': f'{BASE}/panel/brands/{bid}/delete/'}, timeout=30, allow_redirects=True)
        still = s.get(f'{BASE}/panel/brands/?q={slug}', timeout=30)
        if slug in still.text and 'Smoke' in still.text:
            errors.append(('brand_delete', bid, 'still listed'))
            print('FAIL brand still listed')
        else:
            print('OK  brand create+delete', bid)
    else:
        print('WARN could not locate brand id for delete')

    # order detail if link present
    orders = s.get(f'{BASE}/panel/orders/', timeout=30)
    om = re.search(r'/panel/orders/(\d+)/', orders.text)
    if om:
        od = s.get(f'{BASE}/panel/orders/{om.group(1)}/', timeout=30)
        print('OK  order detail', od.status_code, om.group(1))
        if od.status_code >= 400:
            errors.append(('order_detail', om.group(1), od.status_code))

    # stock adjust get
    stock = s.get(f'{BASE}/panel/stock/', timeout=30)
    sm = re.search(r'/panel/stock/(\d+)/adjust/', stock.text)
    if sm:
        sa = s.get(f'{BASE}/panel/stock/{sm.group(1)}/adjust/', timeout=30)
        print('OK  stock adjust form', sa.status_code)

    # backups UI
    b = s.get(f'{BASE}/panel/db/backups/', timeout=30)
    if 'Загрузить' not in b.text and 'import' not in b.text.lower():
        errors.append(('backups', 'import UI', 'missing'))
        print('FAIL backup import UI')
    else:
        print('OK  backup import UI')
    if 'Восстановить' not in b.text:
        print('WARN restore button text missing (need full backup + restore perm)')
    else:
        print('OK  restore UI present')

    # theme toggle
    settings = s.get(f'{BASE}/panel/settings/', timeout=30)
    # theme via dedicated endpoint
    # need csrf from any panel page
    tok = csrf(settings.text) or csrf(s.get(f'{BASE}/panel/', timeout=30).text)
    r = s.post(f'{BASE}/panel/settings/theme/', data={'csrfmiddlewaretoken': tok},
               headers={'Referer': f'{BASE}/panel/settings/'}, timeout=30)
    print('OK  theme', r.status_code)

    print('\n=== SUMMARY ===')
    print('errors', len(errors))
    for e in errors:
        print(' ', e)
    return 1 if errors else 0


if __name__ == '__main__':
    # requests may be missing — use urllib fallback note
    try:
        import requests  # noqa: F401
    except ImportError:
        print('pip install requests')
        raise SystemExit(2)
    raise SystemExit(main())
