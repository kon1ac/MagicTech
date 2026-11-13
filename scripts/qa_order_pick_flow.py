"""Логичный поток: заказ -> ASSEMBLY -> сборка -> PACKED; плюс диагностика бэкапа."""
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

    # Inspect order 92
    od = s.get(f'{BASE}/panel/orders/92/')
    print('order92 status snippet:')
    for pat in [
        r'order_status[^<]{0,40}',
        r'В сборке|Подтверждён|Новый|Оплачен|Собран|Завершён|Отменён',
        r'name="new_status"',
        r'can_change|Статус',
    ]:
        print(' ', pat, bool(re.search(pat, od.text)))
    # visible status text near header
    m = re.search(r'Статус[\s\S]{0,200}', od.text)
    if m:
        print(' status block', re.sub(r'<[^>]+>', ' ', m.group(0))[:200])

    # List orders statuses from table
    orders = s.get(f'{BASE}/panel/orders/')
    rows = re.findall(
        r'(MT-\d+-\d+)[\s\S]{0,400}?(Новый|Подтверждён|Оплачен|В сборке|Собран|Завершён|Отменён)',
        orders.text,
    )
    print('orders sample', rows[:15])

    # Try change status via form if present
    if 'name="new_status"' in od.text:
        tok = csrf(od.text)
        opts = re.findall(r'name="new_status"[\s\S]*?</select>', od.text)
        vals = re.findall(r'<option[^>]+value="([^"]+)"', opts[0]) if opts else []
        print('transitions', vals)
        # prefer ASSEMBLY
        target = 'ASSEMBLY' if 'ASSEMBLY' in vals else (vals[0] if vals else None)
        if target:
            r = s.post(
                f'{BASE}/panel/orders/92/',
                data={
                    'csrfmiddlewaretoken': tok,
                    'new_status': target,
                    'reason': 'QA move to assembly',
                    'viewport': 'desktop',
                },
                headers={'Referer': f'{BASE}/panel/orders/92/'},
                allow_redirects=True,
            )
            print('status change', target, r.url)
            alerts = re.findall(r'message[^>]*>([^<]+)', r.text)
            print(' alerts', alerts[:5])
    else:
        print('NO new_status form on order detail — permission or no transitions')

    # Find any ASSEMBLY order
    picking = s.get(f'{BASE}/panel/picking/')
    print('picking empty?', 'Нет заданий' in picking.text or 'нет заказ' in picking.text.lower())
    print('picking text sample', re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', picking.text))[200:500])

    # Django ORM path via manage.py for status + pick
    print('--- use manage shell for reliable transition ---')


if __name__ == '__main__':
    main()
