"""Диагностика бэкапа (текст ошибки) и расшифровки ПДн."""
from __future__ import annotations

import re

import requests

BASE = 'http://127.0.0.1:8000'


def csrf(html: str) -> str:
    m = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)', html)
    return m.group(1) if m else ''


def main() -> None:
    s = requests.Session()
    r = s.get(f'{BASE}/panel/login/')
    s.post(
        f'{BASE}/panel/login/',
        data={
            'email': 'db@magtech.local',
            'password': 'DbAdmin123!',
            'csrfmiddlewaretoken': csrf(r.text),
        },
        headers={'Referer': f'{BASE}/panel/login/'},
    )

    b = s.get(f'{BASE}/panel/db/backups/')
    # create form fields
    print('create form snippet:')
    m = re.search(r'action="/panel/db/backups/create/"[\s\S]{0,900}', b.text)
    print(m.group(0) if m else 'NONE')

    r = s.post(
        f'{BASE}/panel/db/backups/create/',
        data={'csrfmiddlewaretoken': csrf(b.text), 'kind': 'full'},
        headers={'Referer': f'{BASE}/panel/db/backups/'},
        allow_redirects=True,
        timeout=180,
    )
    # django messages in templates often in .toast / .alert / ul.messages
    for pat in [
        r'class="[^"]*message[^"]*"[^>]*>([\s\S]*?)</(?:div|li)>',
        r'data-toast[^>]*>([^<]+)',
        r'Ошибка бэкапа[^<]{0,400}',
        r'Резервная копия[^<]{0,200}',
        r'backup_status[^<]{0,80}',
    ]:
        hits = re.findall(pat, r.text, re.I)
        if hits:
            print('PAT', pat[:40], '->', [re.sub(r'<[^>]+>', '', str(h))[:200] for h in hits[:3]])

    # table body
    table = re.search(r'<table[\s\S]{0,5000}</table>', r.text)
    if table:
        rows = re.findall(r'<tr[\s\S]*?</tr>', table.group(0))
        print('table rows', len(rows))
        for row in rows[:6]:
            cells = re.findall(r'<t[dh][^>]*>([\s\S]*?)</t[dh]>', row)
            cells = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', c)).strip()[:60] for c in cells]
            if any(cells):
                print(' ROW', cells)

    # decrypt properly
    users = s.get(f'{BASE}/panel/users/')
    m = re.search(r'/panel/users/(\d+)/decrypt/', users.text)
    uid = m.group(1)
    d = s.get(f'{BASE}/panel/users/{uid}/decrypt/')
    print('decrypt form fields', sorted(set(re.findall(r'name="([^"]+)"', d.text))))
    print('decrypt GET has enc', 'enc:v1:' in d.text)
    r = s.post(
        f'{BASE}/panel/users/{uid}/decrypt/',
        data={
            'csrfmiddlewaretoken': csrf(d.text),
            'confirm': 'on',
            'reason': 'QA full decrypt',
        },
        headers={'Referer': f'{BASE}/panel/users/{uid}/decrypt/'},
        allow_redirects=True,
    )
    print('decrypt POST status', r.status_code)
    print(' warning msg', 'расшифрован' in r.text.lower())
    # look for revealed block
    rev = re.search(r'revealed|Расшифрованн[\s\S]{0,800}', r.text, re.I)
    if rev:
        print(' revealed block', re.sub(r'<[^>]+>', ' ', rev.group(0))[:400])
    else:
        print(' no revealed block; enc still', 'enc:v1:' in r.text)
        # dump interesting parts
        for label in ('Имя', 'Фамилия', 'Телефон', 'first_name', 'phone'):
            if label in r.text:
                idx = r.text.find(label)
                print(' around', label, re.sub(r'<[^>]+>', ' ', r.text[idx : idx + 120]))

    # order transitions doc
    r = s.get(f'{BASE}/panel/orders/49/')
    m = re.search(r'name="new_status"[\s\S]*?</select>', r.text)
    vals = re.findall(r'<option[^>]+value="([^"]*)"[^>]*>([^<]*)', m.group(0)) if m else []
    print('order49 transitions', vals)
    # move PAID -> ASSEMBLY if available
    targets = [v for v, _ in vals if v]
    if 'ASSEMBLY' in targets:
        target = 'ASSEMBLY'
    elif 'CONFIRMED' in targets:
        target = 'CONFIRMED'
    else:
        target = targets[0] if targets else None
    if target:
        r = s.post(
            f'{BASE}/panel/orders/49/',
            data={
                'csrfmiddlewaretoken': csrf(r.text),
                'new_status': target,
                'reason': 'QA chain',
            },
            headers={'Referer': f'{BASE}/panel/orders/49/'},
            allow_redirects=True,
        )
        print('moved 49 to', target, r.url)


if __name__ == '__main__':
    main()
