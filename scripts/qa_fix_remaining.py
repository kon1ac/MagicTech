"""Дожать сбойные действия: товар, акция, склад, бэкап, theme, сборка."""
from __future__ import annotations

import re
import time
from pathlib import Path

import requests

BASE = 'http://127.0.0.1:8000'


def csrf(html: str) -> str:
    m = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)', html)
    return m.group(1) if m else ''


def first_opt(html: str, field: str) -> str:
    m = re.search(rf'name="{field}"[^>]*>[\s\S]*?</select>', html)
    if not m:
        return ''
    vals = re.findall(r'<option[^>]+value="(\d+)"', m.group(0))
    return vals[0] if vals else ''


def main() -> None:
    s = requests.Session()
    r = s.get(f'{BASE}/panel/login/')
    tok = csrf(r.text)
    s.post(
        f'{BASE}/panel/login/',
        data={'email': 'db@magtech.local', 'password': 'DbAdmin123!', 'csrfmiddlewaretoken': tok},
        headers={'Referer': f'{BASE}/panel/login/'},
    )
    ts = int(time.time())
    findings = []

    # Product
    r = s.get(f'{BASE}/panel/products/new/')
    tok = csrf(r.text)
    data = {
        'csrfmiddlewaretoken': tok,
        'product_sku': f'QA-{ts}',
        'product_ean': f'460{ts % 10**10:010d}'[:13],
        'product_name': f'Test QA Product {ts}',
        'id_brand': first_opt(r.text, 'id_brand') or '16',
        'id_category': first_opt(r.text, 'id_category') or '28',
        'id_unit': first_opt(r.text, 'id_unit'),
        'cost_price': '1500.00',
        'is_active': 'on',
        'price': '9999.00',
        'price_reason': 'QA initial price',
        'product_description': 'QA product',
        'product_characteristics': '{"color":"black"}',
        'seo_title': '',
        'seo_description': '',
        'seo_keywords': '',
        'viewport': 'desktop',
    }
    print('product payload keys', {k: data[k] for k in ('id_brand', 'id_category', 'id_unit', 'product_sku')})
    r = s.post(
        f'{BASE}/panel/products/new/',
        data=data,
        headers={'Referer': f'{BASE}/panel/products/new/'},
        allow_redirects=True,
    )
    print('PRODUCT', r.status_code, r.url)
    if '/products/new' in r.url:
        findings.append('product create')
        for err in re.findall(r'<li>([^<]{3,120})</li>', r.text)[:10]:
            print('  li', err)
        # field errors
        for err in re.findall(r'class="[^"]*error[^"]*"[^>]*>([^<]+)', r.text)[:10]:
            print('  err', err)
    else:
        print('OK product')

    # Stock adjust
    stock = s.get(f'{BASE}/panel/stock/')
    sm = re.search(r'/panel/stock/(\d+)/adjust/', stock.text)
    if sm:
        pid = sm.group(1)
        adj = s.get(f'{BASE}/panel/stock/{pid}/adjust/')
        tok = csrf(adj.text)
        r = s.post(
            f'{BASE}/panel/stock/{pid}/adjust/',
            data={
                'csrfmiddlewaretoken': tok,
                'delta': '5',
                'reason': 'QA adjust +5',
                'confirm': 'on',
                'viewport': 'desktop',
            },
            headers={'Referer': f'{BASE}/panel/stock/{pid}/adjust/'},
            allow_redirects=True,
        )
        print('ADJUST', r.status_code, r.url)
        if f'/stock/{pid}/adjust' in r.url:
            findings.append('stock adjust stayed on form')
            for err in re.findall(r'<li>([^<]{3,120})</li>', r.text)[:5]:
                print('  li', err)
            # check template expects confirm differently
            print('  has confirm checkbox', 'name="confirm"' in adj.text)

    # Stock receipt
    rec = s.get(f'{BASE}/panel/stock/receipt/')
    tok = csrf(rec.text)
    prod = first_opt(rec.text, 'product')
    r = s.post(
        f'{BASE}/panel/stock/receipt/',
        data={
            'csrfmiddlewaretoken': tok,
            'product': prod,
            'quantity': '3',
            'expected_quantity': '3',
            'document_number': f'QA-IN-{ts}',
            'reason': 'QA receipt',
            'viewport': 'desktop',
        },
        headers={'Referer': f'{BASE}/panel/stock/receipt/'},
        allow_redirects=True,
    )
    print('RECEIPT', r.status_code, r.url, 'prod', prod)
    if '/receipt' in r.url and r.status_code == 200:
        for err in re.findall(r'<li>([^<]{3,120})</li>', r.text)[:5]:
            print('  li', err)

    # Promotion
    r = s.get(f'{BASE}/panel/promotions/new/')
    tok = csrf(r.text)
    # dump required-looking fields / types
    print('promo type opts', re.findall(r'name="promotion_type"[\s\S]*?</select>', r.text)[:1])
    ptype = first_opt(r.text, 'promotion_type')
    # also non-numeric options
    m = re.search(r'name="promotion_type"[\s\S]*?</select>', r.text)
    if m:
        opts = re.findall(r'<option[^>]+value="([^"]*)"', m.group(0))
        print('promo type values', opts)
        ptype = next((o for o in opts if o), '')
    pdata = {
        'csrfmiddlewaretoken': tok,
        'promotion_name': f'QA Promo {ts}',
        'promotion_type': ptype,
        'promotion_value': '10',
        'promotion_promo_code': f'QA{ts}',
        'promotion_description': 'qa',
        'promotion_min_qty': '1',
        'promotion_min_sum': '0',
        'start_at': '2026-11-01T00:00',
        'end_at': '2026-12-31T23:59',
        'usage_limit': '100',
        'is_active': 'on',
        'is_stackable': 'on',
        'viewport': 'desktop',
    }
    r = s.post(
        f'{BASE}/panel/promotions/new/',
        data=pdata,
        headers={'Referer': f'{BASE}/panel/promotions/new/'},
        allow_redirects=True,
    )
    print('PROMO', r.status_code, r.url)
    if '/promotions/new' in r.url:
        findings.append('promo create')
        for err in re.findall(r'<li>([^<]{3,200})</li>', r.text)[:10]:
            print('  li', err)

    # Backup create — inspect view response body messages
    b = s.get(f'{BASE}/panel/db/backups/')
    tok = csrf(b.text)
    before = set(re.findall(r'href="(/panel/db/backups/[^"]+)"', b.text))
    r = s.post(
        f'{BASE}/panel/db/backups/create/',
        data={'csrfmiddlewaretoken': tok, 'viewport': 'desktop'},
        headers={'Referer': f'{BASE}/panel/db/backups/'},
        allow_redirects=True,
        timeout=180,
    )
    after = set(re.findall(r'href="(/panel/db/backups/[^"]+)"', r.text))
    print('BACKUP', r.status_code, 'new links', after - before)
    msgs = re.findall(r'messages?__item|alert|toast|flash', r.text, re.I)
    # django messages
    for m in re.findall(r'data-toast[^>]*>([^<]+)|class="[^"]*message[^"]*"[^>]*>([^<]+)', r.text)[:5]:
        print('  msg', m)
    # search for .dump or backup file names
    files = re.findall(r'[\w\-]+\.(?:dump|backup|sql|fc)', r.text)
    print('  files on page', files[:10])
    if not (after - before) and not files:
        findings.append('backup create no visible new file')

    # Theme needs theme=light|dark
    r = s.post(
        f'{BASE}/panel/settings/theme/',
        data={'csrfmiddlewaretoken': csrf(s.get(f'{BASE}/panel/settings/').text), 'theme': 'light'},
        headers={'Referer': f'{BASE}/panel/settings/', 'X-Requested-With': 'XMLHttpRequest'},
    )
    print('THEME', r.status_code, r.text[:200])
    if r.status_code >= 400:
        findings.append(f'theme {r.status_code}')

    # Picking — open and try complete
    picking = s.get(f'{BASE}/panel/picking/')
    hrefs = re.findall(r'href="(/panel/picking/[^"]+)"', picking.text)
    print('PICKING hrefs', hrefs[:10])
    for href in hrefs[:5]:
        pr = s.get(f'{BASE}{href}')
        print(' ', href, pr.status_code, 'forms', len(re.findall(r'<form', pr.text)))
        if 'csrfmiddlewaretoken' in pr.text:
            names = sorted(set(re.findall(r'name="([^"]+)"', pr.text)))
            print('   fields', names)
            tok = csrf(pr.text)
            pdata = {'csrfmiddlewaretoken': tok, 'viewport': 'desktop'}
            for n in names:
                if n in ('csrfmiddlewaretoken', 'viewport'):
                    continue
                if n in ('confirm', 'confirmed', 'done'):
                    pdata[n] = 'on'
                else:
                    pdata[n] = first_opt(pr.text, n) or '1'
            # only POST if looks like action form
            if any(x in pr.text.lower() for x in ('заверш', 'собрать', 'confirm', 'complete', 'взять')):
                r = s.post(
                    f'{BASE}{href}',
                    data=pdata,
                    headers={'Referer': f'{BASE}{href}'},
                    allow_redirects=True,
                )
                print('   POST', r.status_code, r.url)

    # Order status transitions
    orders = s.get(f'{BASE}/panel/orders/')
    oid = re.search(r'/panel/orders/(\d+)/', orders.text)
    if oid:
        od = s.get(f'{BASE}/panel/orders/{oid.group(1)}/')
        print('ORDER', oid.group(1), 'status codes buttons:')
        print('  forms', re.findall(r'<form[^>]+action="([^"]*)"', od.text)[:10])
        print('  buttons', re.findall(r'<(?:button|input)[^>]*(?:value|name)="([^"]+)"[^>]*>', od.text)[:20])
        # status select
        if 'name="status"' in od.text or 'name="new_status"' in od.text:
            tok = csrf(od.text)
            field = 'new_status' if 'name="new_status"' in od.text else 'status'
            m = re.search(rf'name="{field}"[\s\S]*?</select>', od.text)
            opts = re.findall(r'<option[^>]+value="([^"]+)"', m.group(0)) if m else []
            print('  status opts', opts)

    print('FINDINGS', findings)
    Path(__file__).with_name('qa_fix_log.txt').write_text('\n'.join(findings), encoding='utf-8')


if __name__ == '__main__':
    main()
