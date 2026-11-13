"""Сборка заказа ASSEMBLY + диагностика бэкапа."""
from __future__ import annotations

import os
import re
import sys

import requests

BASE = 'http://127.0.0.1:8000'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    picking = s.get(f'{BASE}/panel/picking/')
    hrefs = [h for h in re.findall(r'href="([^"]+)"', picking.text) if 'pick' in h or '/orders/' in h]
    print('pick-related hrefs', hrefs[:30])

    for oid in (99, 47, 101):
        path = f'/panel/orders/{oid}/pick/'
        r = s.get(f'{BASE}{path}')
        print('GET', path, r.status_code)
        if r.status_code != 200:
            continue
        tok = csrf(r.text)
        item_ids = re.findall(r'name="picked"[^>]*value="(\d+)"', r.text)
        if not item_ids:
            item_ids = re.findall(r'value="(\d+)"[^>]*name="picked"', r.text)
        print(' items', item_ids)
        data = [('csrfmiddlewaretoken', tok), ('confirm', 'on'), ('viewport', 'desktop')]
        for i in item_ids:
            data.append(('picked', i))
        r2 = s.post(f'{BASE}{path}', data=data, headers={'Referer': f'{BASE}{path}'}, allow_redirects=True)
        print(' POST', r2.status_code, r2.url)
        plain = re.sub(r'<[^>]+>', ' ', r2.text)
        if 'собран' in plain.lower() or 'Собран' in plain:
            print(' SUCCESS pick order', oid)
            break
        for a in re.findall(r'(error|success|alert|message)[^>]*>([^<]{5,160})', r2.text, re.I)[:6]:
            print(' msg', a)

    # Backup via django
    sys.path.insert(0, ROOT)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from users.models import User
    from shop.services import dbadmin

    u = User.objects.get(email='db@magtech.local')
    try:
        rec = dbadmin.create_backup('full', actor=u, request=None)
        print('create_backup', rec.pk, rec.backup_status, getattr(rec, 'file_path', None))
        print('output tail', (getattr(rec, 'backup_output', None) or '')[-500:])
    except Exception as e:
        print('create_backup EXC', type(e).__name__, e)

    from django.apps import apps
    for m in apps.get_models():
        if 'backup' in m.__name__.lower():
            print('model', m.__name__, 'count', m.objects.count())
            for row in m.objects.order_by('-pk')[:5]:
                print(
                    ' ',
                    row.pk,
                    getattr(row, 'backup_status', None),
                    getattr(row, 'file_path', None),
                    getattr(row, 'verify_status', None),
                )


if __name__ == '__main__':
    main()
