"""Финальный проход действий: сборка, статус, бэкап, расшифровка, приход."""
from __future__ import annotations

import re

import requests

BASE = 'http://127.0.0.1:8000'


def csrf(html: str) -> str:
    m = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)', html)
    return m.group(1) if m else ''


def plain(html: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html))


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

    # Pick order 47
    path = '/panel/orders/47/pick/'
    r = s.get(f'{BASE}{path}')
    ids = re.findall(r'name="picked"[^>]*value="(\d+)"', r.text) or re.findall(
        r'value="(\d+)"[^>]*name="picked"', r.text
    )
    data = [('csrfmiddlewaretoken', csrf(r.text)), ('confirm', 'on')] + [('picked', i) for i in ids]
    r = s.post(f'{BASE}{path}', data=data, headers={'Referer': f'{BASE}{path}'}, allow_redirects=True)
    print('PICK47', r.url, 'ok' if '/orders/47/' in r.url and path not in r.url else 'maybe-fail')
    print(' ', [m for m in re.findall(r'.{0,40}(собран|ошибк|Списан|PACKED).{0,40}', plain(r.text), re.I)][:3])

    # Status change on NEW order 90
    r = s.get(f'{BASE}/panel/orders/90/')
    print('ORDER90 has form', 'name="new_status"' in r.text)
    m = re.search(r'name="new_status"[\s\S]*?</select>', r.text)
    if m:
        vals = [v for v in re.findall(r'<option[^>]+value="([^"]*)"', m.group(0)) if v]
        print(' transitions', vals)
        target = 'CONFIRMED' if 'CONFIRMED' in vals else vals[0]
        r = s.post(
            f'{BASE}/panel/orders/90/',
            data={
                'csrfmiddlewaretoken': csrf(r.text),
                'new_status': target,
                'reason': 'QA status change',
            },
            headers={'Referer': f'{BASE}/panel/orders/90/'},
            allow_redirects=True,
        )
        print('CHG90', target, r.url)
        print(' ', [x for x in re.findall(r'.{0,20}(обновлён|ошибк|Статус).{0,40}', plain(r.text), re.I)][:3])

    # Stock receipt already tested; adjust product 267
    r = s.get(f'{BASE}/panel/stock/267/adjust/')
    if r.status_code == 200:
        r2 = s.post(
            f'{BASE}/panel/stock/267/adjust/',
            data={
                'csrfmiddlewaretoken': csrf(r.text),
                'delta': '15',
                'reason': 'QA stock for new product',
                'confirm': 'on',
            },
            headers={'Referer': f'{BASE}/panel/stock/267/adjust/'},
            allow_redirects=True,
        )
        print('ADJUST267', r2.url)

    # Backup
    b = s.get(f'{BASE}/panel/db/backups/')
    before_files = re.findall(r'[\w.\-]+\.dump', b.text)
    r = s.post(
        f'{BASE}/panel/db/backups/create/',
        data={'csrfmiddlewaretoken': csrf(b.text), 'kind': 'full'},
        headers={'Referer': f'{BASE}/panel/db/backups/'},
        allow_redirects=True,
        timeout=180,
    )
    after_files = re.findall(r'[\w.\-]+\.dump', r.text)
    print('BACKUP files before/after', before_files[:5], after_files[:5])
    print(' restore UI', 'Восстановить' in r.text, 'import UI', 'Загрузить' in r.text or 'import' in r.text.lower())
    for msg in re.findall(r'(Резервная копия[^.!]{0,80}|Ошибка бэкапа[^.!]{0,120}|Дамп импортирован[^.!]{0,80})', plain(r.text)):
        print(' MSG', msg)

    # Inspect BackupRecord via ORM through a tiny manage call is hard; parse table rows
    rows = re.findall(r'(success|failed|error|pending|running)', r.text, re.I)
    print(' status words', rows[:20])

    # Decrypt
    users = s.get(f'{BASE}/panel/users/')
    print('PII cipher', 'enc:v1:' in users.text)
    m = re.search(r'/panel/users/(\d+)/decrypt/', users.text)
    if m:
        d = s.get(f'{BASE}{m.group(0)}')
        r = s.post(
            f'{BASE}{m.group(0)}',
            data={'csrfmiddlewaretoken': csrf(d.text), 'confirm': '1', 'reason': 'QA decrypt Opera pass'},
            headers={'Referer': f'{BASE}{m.group(0)}'},
            allow_redirects=True,
        )
        p = plain(r.text)
        print('DECRYPT', m.group(1), 'still_cipher', 'enc:v1:' in r.text)
        # look for phone-like or name fields
        print(' revealed sample', re.findall(r'(Имя|Телефон|Фамилия)\s*[:\s]+([^\s]{2,40})', p)[:6])

    # Paid order -> try move toward assembly chain if possible
    r = s.get(f'{BASE}/panel/orders/49/')  # Оплачен from earlier sample
    print('ORDER49 form', 'name="new_status"' in r.text)
    m = re.search(r'name="new_status"[\s\S]*?</select>', r.text)
    if m:
        vals = [v for v in re.findall(r'<option[^>]+value="([^"]*)"', m.group(0)) if v]
        print(' ORDER49 transitions', vals)

    # Reviews moderate
    rev = s.get(f'{BASE}/panel/reviews/')
    print('REVIEWS', rev.status_code, 'actions', re.findall(r'href="(/panel/reviews/[^"]+)"', rev.text)[:8])

    # IO
    io = s.get(f'{BASE}/panel/io/')
    print('IO', io.status_code, 'forms', re.findall(r'<form[^>]+action="([^"]*)"', io.text)[:8])

    print('DONE')


if __name__ == '__main__':
    main()
