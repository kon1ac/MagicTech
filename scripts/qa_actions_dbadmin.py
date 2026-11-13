"""Полный сценарий действий DB_ADMIN через HTTP (зеркало кликов в UI)."""
from __future__ import annotations

import re
import time
from pathlib import Path

import requests

BASE = 'http://127.0.0.1:8000'
EMAIL = 'db@magtech.local'
PASSWORD = 'DbAdmin123!'
LOG = Path(__file__).resolve().parent / 'qa_actions_log.txt'


def csrf(html: str) -> str:
    m = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)', html)
    return m.group(1) if m else ''


def log(msg: str) -> None:
    line = msg
    print(line)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(line + '\n')


def main() -> int:
    LOG.write_text('', encoding='utf-8')
    s = requests.Session()
    findings: list[str] = []
    ts = int(time.time())

    r = s.get(f'{BASE}/panel/login/', timeout=30)
    tok = csrf(r.text)
    r = s.post(
        f'{BASE}/panel/login/',
        data={'email': EMAIL, 'password': PASSWORD, 'csrfmiddlewaretoken': tok},
        headers={'Referer': f'{BASE}/panel/login/'},
        timeout=30,
        allow_redirects=True,
    )
    if '/panel/login' in r.url and 'Неверный' in r.text:
        log('FAIL login')
        return 1
    log(f'OK login -> {r.url}')

    # --- 1. Category ---
    r = s.get(f'{BASE}/panel/categories/new/', timeout=30)
    tok = csrf(r.text)
    fields = sorted(set(re.findall(r'name="([^"]+)"', r.text)))
    log(f'category fields: {fields}')
    # detect real field names from form
    data = {'csrfmiddlewaretoken': tok, 'is_active': 'on'}
    for name in fields:
        if name == 'csrfmiddlewaretoken':
            continue
        if 'name' in name and 'brand' not in name:
            data[name] = f'Тест QA Категория {ts}'
        elif 'slug' in name:
            data[name] = f'test-qa-cat-{ts}'
        elif 'parent' in name:
            data[name] = ''
        elif 'filter' in name or 'attr' in name:
            data[name] = '{"filters": ["color"]}'
        elif name == 'is_active':
            data[name] = 'on'
        else:
            data[name] = ''
    # ModelForm typically uses model field names
    if 'name' not in data and 'category_name' not in data:
        data['name'] = f'Тест QA Категория {ts}'
        data['slug'] = f'test-qa-cat-{ts}'
    r = s.post(
        f'{BASE}/panel/categories/new/',
        data=data,
        headers={'Referer': f'{BASE}/panel/categories/new/'},
        timeout=30,
        allow_redirects=True,
    )
    ok = r.status_code < 400 and '/categories/new' not in r.url
    if not ok:
        errs = re.findall(r'errorlist[^>]*>(.*?)</ul>', r.text, re.S)
        log(f'FAIL category create url={r.url} errs={errs[:2]}')
        findings.append('category create failed')
        # dump first 500 of form errors
        if 'error' in r.text.lower():
            m = re.search(r'class="[^"]*error[^"]*"[^>]*>([^<]+)', r.text)
            if m:
                log(f'  err text: {m.group(1)[:200]}')
    else:
        log(f'OK category create -> {r.url}')
    cat_id = None
    m = re.search(rf'test-qa-cat-{ts}.*?/panel/categories/(\d+)/', r.text, re.S)
    if not m:
        listing = s.get(f'{BASE}/panel/categories/?q=test-qa-cat-{ts}', timeout=30)
        m = re.search(r'/panel/categories/(\d+)/', listing.text)
    if m:
        cat_id = m.group(1)
        log(f'OK category id={cat_id}')

    # --- 2. Brand ---
    r = s.get(f'{BASE}/panel/brands/new/', timeout=30)
    tok = csrf(r.text)
    fields = sorted(set(re.findall(r'name="([^"]+)"', r.text)))
    log(f'brand fields: {fields}')
    bslug = f'test-qa-brand-{ts}'
    data = {'csrfmiddlewaretoken': tok}
    for name in fields:
        if name == 'csrfmiddlewaretoken':
            continue
        if name in ('brand_name', 'name'):
            data[name] = f'Тест QA Бренд {ts}'
        elif name in ('brand_slug', 'slug'):
            data[name] = bslug
        elif 'desc' in name:
            data[name] = 'qa brand'
        elif name == 'is_active':
            data[name] = 'on'
        else:
            data.setdefault(name, '')
    data.setdefault('brand_name', f'Тест QA Бренд {ts}')
    data.setdefault('brand_slug', bslug)
    data.setdefault('is_active', 'on')
    r = s.post(
        f'{BASE}/panel/brands/new/',
        data=data,
        headers={'Referer': f'{BASE}/panel/brands/new/'},
        timeout=30,
        allow_redirects=True,
    )
    ok = '/brands/new' not in r.url
    log(f'{"OK" if ok else "FAIL"} brand create -> {r.url}')
    if not ok:
        findings.append('brand create failed')
    brand_id = None
    listing = s.get(f'{BASE}/panel/brands/?q={bslug}', timeout=30)
    m = re.search(rf'{bslug}.*?/panel/brands/(\d+)/', listing.text, re.S) or re.search(
        r'/panel/brands/(\d+)/edit/', listing.text
    )
    if m:
        brand_id = m.group(1)
        log(f'OK brand id={brand_id}')

    # --- 3. Product ---
    r = s.get(f'{BASE}/panel/products/new/', timeout=30)
    tok = csrf(r.text)
    fields = sorted(set(re.findall(r'name="([^"]+)"', r.text)))
    log(f'product fields: {fields}')
    # parse select options for category/brand
    def first_option(html: str, field: str) -> str:
        m = re.search(
            rf'name="{field}"[^>]*>.*?<option[^>]+value="(\d+)"',
            html,
            re.S,
        )
        return m.group(1) if m else ''

    sku = f'QA-{ts}'
    pdata = {'csrfmiddlewaretoken': tok}
    for name in fields:
        if name == 'csrfmiddlewaretoken':
            continue
        if name in ('product_name', 'name', 'title'):
            pdata[name] = f'Тест QA Товар {ts}'
        elif name == 'sku':
            pdata[name] = sku
        elif name in ('slug', 'product_slug'):
            pdata[name] = f'test-qa-product-{ts}'
        elif name in ('price', 'base_price', 'price_amount'):
            pdata[name] = '9999.00'
        elif name in ('stock', 'stock_qty', 'quantity'):
            pdata[name] = '10'
        elif name in ('category', 'category_id'):
            pdata[name] = cat_id or first_option(r.text, name)
        elif name in ('brand', 'brand_id'):
            pdata[name] = brand_id or first_option(r.text, name)
        elif name == 'is_active':
            pdata[name] = 'on'
        elif name in ('description', 'short_description', 'full_description'):
            pdata[name] = 'QA product description'
        elif name in ('status',):
            # pick first non-empty option
            pdata[name] = first_option(r.text, name) or 'published'
        else:
            # try select first option if select
            if f'name="{name}"' in r.text and '<select' in r.text[
                max(0, r.text.find(f'name="{name}"') - 80) : r.text.find(f'name="{name}"') + 20
            ]:
                pdata[name] = first_option(r.text, name)
            else:
                pdata.setdefault(name, '')
    # common defaults
    pdata.setdefault('sku', sku)
    pdata.setdefault('price', '9999.00')
    if cat_id:
        pdata.setdefault('category', cat_id)
    if brand_id:
        pdata.setdefault('brand', brand_id)
    r = s.post(
        f'{BASE}/panel/products/new/',
        data=pdata,
        headers={'Referer': f'{BASE}/panel/products/new/'},
        timeout=60,
        allow_redirects=True,
    )
    ok = '/products/new' not in r.url
    log(f'{"OK" if ok else "FAIL"} product create -> {r.url}')
    if not ok:
        findings.append('product create failed')
        # extract validation
        for err in re.findall(r'<li>([^<]{3,120})</li>', r.text)[:8]:
            log(f'  li: {err}')
    product_id = None
    listing = s.get(f'{BASE}/panel/products/?q={sku}', timeout=30)
    m = re.search(r'/panel/products/(\d+)/', listing.text)
    if m:
        product_id = m.group(1)
        log(f'OK product id={product_id} sku={sku}')

    # --- 4. Stock receipt / adjust ---
    stock = s.get(f'{BASE}/panel/stock/', timeout=30)
    log(f'OK stock list {stock.status_code}')
    sm = re.search(r'/panel/stock/(\d+)/adjust/', stock.text)
    if sm:
        adj = s.get(f'{BASE}/panel/stock/{sm.group(1)}/adjust/', timeout=30)
        tok = csrf(adj.text)
        fields = sorted(set(re.findall(r'name="([^"]+)"', adj.text)))
        log(f'adjust fields: {fields}')
        adata = {'csrfmiddlewaretoken': tok}
        for name in fields:
            if name == 'csrfmiddlewaretoken':
                continue
            if 'qty' in name or 'quantity' in name or 'delta' in name or name == 'amount':
                adata[name] = '5'
            elif 'reason' in name or 'comment' in name or 'note' in name:
                adata[name] = 'QA adjust +5'
            elif name == 'direction' or name == 'type':
                adata[name] = first_option(adj.text, name) or 'in'
            else:
                adata[name] = first_option(adj.text, name) or ''
        r = s.post(
            f'{BASE}/panel/stock/{sm.group(1)}/adjust/',
            data=adata,
            headers={'Referer': f'{BASE}/panel/stock/{sm.group(1)}/adjust/'},
            timeout=30,
            allow_redirects=True,
        )
        log(f'{"OK" if r.status_code < 400 else "FAIL"} stock adjust -> {r.url}')
    receipt = s.get(f'{BASE}/panel/stock/receipt/', timeout=30)
    log(f'OK stock receipt page {receipt.status_code}')
    if receipt.status_code == 200:
        tok = csrf(receipt.text)
        fields = sorted(set(re.findall(r'name="([^"]+)"', receipt.text)))
        log(f'receipt fields: {fields}')

    # --- 5. Orders + picking ---
    orders = s.get(f'{BASE}/panel/orders/', timeout=30)
    log(f'OK orders {orders.status_code}')
    om = re.search(r'/panel/orders/(\d+)/', orders.text)
    order_id = om.group(1) if om else None
    if order_id:
        od = s.get(f'{BASE}/panel/orders/{order_id}/', timeout=30)
        log(f'OK order detail {order_id} {od.status_code}')
        # try status change forms
        tok = csrf(od.text)
        # any post buttons with name=action
        actions = re.findall(r'name="(action|status|new_status)"[^>]*value="([^"]+)"', od.text)
        log(f'order actions: {actions[:10]}')
        for aname, aval in actions[:1]:
            r = s.post(
                f'{BASE}/panel/orders/{order_id}/',
                data={'csrfmiddlewaretoken': tok, aname: aval},
                headers={'Referer': f'{BASE}/panel/orders/{order_id}/'},
                timeout=30,
                allow_redirects=True,
            )
            log(f'order post {aname}={aval} -> {r.status_code} {r.url}')

    picking = s.get(f'{BASE}/panel/picking/', timeout=30)
    log(f'OK picking {picking.status_code}')
    pm = re.search(r'/panel/picking/(\d+)/', picking.text) or re.search(
        r'href="(/panel/picking/[^"]+)"', picking.text
    )
    if pm:
        path = pm.group(1) if pm.group(0).startswith('href') else f'/panel/picking/{pm.group(1)}/'
        if not path.startswith('/'):
            path = f'/panel/picking/{pm.group(1)}/'
        # fix if group is full path
        if 'href=' in str(pm.group(0)):
            path = pm.group(1)
        else:
            path = f'/panel/picking/{pm.group(1)}/'
        # better: search full hrefs
        hrefs = re.findall(r'href="(/panel/picking/[^"]+)"', picking.text)
        log(f'picking hrefs: {hrefs[:8]}')
        for href in hrefs[:3]:
            pr = s.get(f'{BASE}{href}', timeout=30)
            log(f'  picking GET {href} -> {pr.status_code}')
            if pr.status_code == 200 and 'csrfmiddlewaretoken' in pr.text:
                tok = csrf(pr.text)
                # try complete / pick actions
                btn_vals = re.findall(
                    r'<(?:button|input)[^>]+(?:name|value)="([^"]*(?:pick|complete|done|confirm|assemble)[^"]*)"',
                    pr.text,
                    re.I,
                )
                log(f'  pick buttons: {btn_vals[:8]}')
                # generic confirm post if form present
                if 'confirm' in pr.text.lower() or 'собрать' in pr.text.lower() or 'заверш' in pr.text.lower():
                    # find all named inputs
                    names = sorted(set(re.findall(r'name="([^"]+)"', pr.text)))
                    pdata2 = {'csrfmiddlewaretoken': tok}
                    for n in names:
                        if n == 'csrfmiddlewaretoken':
                            continue
                        if n in ('confirm', 'confirmed'):
                            pdata2[n] = '1'
                        else:
                            pdata2[n] = first_option(pr.text, n) or '1'
                    r = s.post(
                        f'{BASE}{href}',
                        data=pdata2,
                        headers={'Referer': f'{BASE}{href}'},
                        timeout=30,
                        allow_redirects=True,
                    )
                    log(f'  picking POST {href} -> {r.status_code} {r.url}')

    # --- 6. Promotions ---
    r = s.get(f'{BASE}/panel/promotions/new/', timeout=30)
    tok = csrf(r.text)
    fields = sorted(set(re.findall(r'name="([^"]+)"', r.text)))
    log(f'promo fields: {fields}')
    pdata = {'csrfmiddlewaretoken': tok, 'is_active': 'on'}
    for name in fields:
        if name == 'csrfmiddlewaretoken':
            continue
        if 'name' in name or name == 'title':
            pdata[name] = f'QA Акция {ts}'
        elif 'slug' in name:
            pdata[name] = f'qa-promo-{ts}'
        elif 'discount' in name or 'percent' in name:
            pdata[name] = '10'
        elif 'desc' in name:
            pdata[name] = 'qa'
        elif name == 'is_active':
            pdata[name] = 'on'
        else:
            pdata.setdefault(name, first_option(r.text, name) or '')
    r = s.post(
        f'{BASE}/panel/promotions/new/',
        data=pdata,
        headers={'Referer': f'{BASE}/panel/promotions/new/'},
        timeout=30,
        allow_redirects=True,
    )
    log(f'{"OK" if "/promotions/new" not in r.url else "FAIL"} promo -> {r.url}')

    # --- 7. Users decrypt ---
    users = s.get(f'{BASE}/panel/users/', timeout=30)
    if 'enc:v1:' in users.text:
        log('OK users list shows enc:v1: ciphertext')
    else:
        log('WARN no enc:v1: on users list')
        findings.append('users list missing enc:v1:')
    m = re.search(r'/panel/users/(\d+)/decrypt/', users.text)
    if m:
        uid = m.group(1)
        d = s.get(f'{BASE}/panel/users/{uid}/decrypt/', timeout=30)
        tok = csrf(d.text)
        r = s.post(
            f'{BASE}/panel/users/{uid}/decrypt/',
            data={'csrfmiddlewaretoken': tok, 'confirm': '1', 'reason': 'QA decrypt test'},
            headers={'Referer': f'{BASE}/panel/users/{uid}/decrypt/'},
            timeout=30,
            allow_redirects=True,
        )
        log(f'OK decrypt user {uid} status={r.status_code} revealed={"enc:v1:" not in r.text or "Имя" in r.text}')
    else:
        log('WARN no decrypt link')
        findings.append('no decrypt link')

    # --- 8. Backups create ---
    b = s.get(f'{BASE}/panel/db/backups/', timeout=30)
    log(f'OK backups page {b.status_code} import_ui={"Загрузить" in b.text or "import" in b.text.lower()} restore_ui={"Восстановить" in b.text}')
    tok = csrf(b.text)
    # find create form action
    if 'создать' in b.text.lower() or 'create' in b.text.lower() or 'backup' in b.text.lower():
        # try common endpoints
        for path in [
            '/panel/db/backups/create/',
            '/panel/db/backups/',
        ]:
            page = s.get(f'{BASE}{path}', timeout=30) if path.endswith('create/') else b
            if page.status_code >= 400 and path.endswith('create/'):
                continue
            tok = csrf(page.text) or tok
            # look for form posting to create
            actions = re.findall(r'<form[^>]+action="([^"]*)"', page.text)
            log(f'backup forms actions: {actions}')
            # POST create with empty/minimal
            r = s.post(
                f'{BASE}/panel/db/backups/',
                data={'csrfmiddlewaretoken': tok, 'action': 'create', 'label': f'qa-{ts}'},
                headers={'Referer': f'{BASE}/panel/db/backups/'},
                timeout=120,
                allow_redirects=True,
            )
            log(f'backup POST / -> {r.status_code} {r.url}')
            # alternate create URL
            r2 = s.post(
                f'{BASE}/panel/db/backups/create/',
                data={'csrfmiddlewaretoken': tok, 'label': f'qa-{ts}'},
                headers={'Referer': f'{BASE}/panel/db/backups/'},
                timeout=120,
                allow_redirects=True,
            )
            log(f'backup POST /create/ -> {r2.status_code} {r2.url}')
            break

    # list backup files / restore links
    b2 = s.get(f'{BASE}/panel/db/backups/', timeout=30)
    restore_links = re.findall(r'href="(/panel/db/backups/[^"]*restore[^"]*)"', b2.text)
    download_links = re.findall(r'href="(/panel/db/backups/[^"]*(?:download|file)[^"]*)"', b2.text)
    log(f'restore links: {restore_links[:5]} download: {download_links[:5]}')

    # --- 9. Reviews / payments / returns / audit / settings ---
    for path in [
        '/panel/reviews/',
        '/panel/payments/',
        '/panel/statements/',
        '/panel/returns/',
        '/panel/io/',
        '/panel/audit/',
        '/panel/settings/',
        '/panel/db/',
        '/panel/db/schema/',
        '/panel/db/jobs/',
        '/panel/archive/',
        '/panel/references/',
        '/panel/reports/',
        '/panel/users/rbac/',
        '/panel/characteristics/',
        '/panel/products/?chart_period=7d',
        '/panel/promotions/?chart_period=90d',
    ]:
        resp = s.get(f'{BASE}{path}', timeout=60)
        flag = 'OK' if resp.status_code < 400 else 'FAIL'
        if resp.status_code >= 400:
            findings.append(f'{flag} {path} {resp.status_code}')
        log(f'{flag} GET {path} {resp.status_code}')

    # theme toggle
    settings = s.get(f'{BASE}/panel/settings/', timeout=30)
    tok = csrf(settings.text)
    r = s.post(
        f'{BASE}/panel/settings/theme/',
        data={'csrfmiddlewaretoken': tok},
        headers={'Referer': f'{BASE}/panel/settings/'},
        timeout=30,
        allow_redirects=True,
    )
    log(f'OK theme toggle {r.status_code}')

    log('=== FINDINGS ===')
    for f in findings:
        log(f'  - {f}')
    log(f'total findings: {len(findings)}')
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
