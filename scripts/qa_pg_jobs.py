"""Проверка бэкапа и run_job после фикса PG_BIN."""
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
    before = set(re.findall(r'MagicTech_\w+_\d+_\d+\.dump', b.text))
    r = s.post(
        f'{BASE}/panel/db/backups/create/',
        data={'csrfmiddlewaretoken': csrf(b.text), 'kind': 'full'},
        headers={'Referer': f'{BASE}/panel/db/backups/'},
        allow_redirects=True,
        timeout=180,
    )
    after = set(re.findall(r'MagicTech_\w+_\d+_\d+\.dump', r.text))
    plain = re.sub(r'<[^>]+>', ' ', r.text)
    print('BACKUP UI')
    print('  new dumps', after - before)
    print('  has restore', 'Восстановить' in r.text)
    for msg in re.findall(r'(Резервная копия[^.!]{0,100}|Ошибка бэкапа[^.!]{0,120}|Не найдена утилита[^.!]{0,80})', plain):
        print('  MSG', msg.strip())

    # jobs page — find run action
    jobs = s.get(f'{BASE}/panel/db/jobs/')
    print('JOBS page', jobs.status_code)
    actions = re.findall(r'action="(/panel/db/jobs/[^"]+)"', jobs.text)
    print('  form actions', actions[:10])
    # also button names
    print('  run-like', re.findall(r'(run|запуст|execute|action)[^"]{0,40}', jobs.text, re.I)[:15])

    # try POST run on each job that has run endpoint
    for href in re.findall(r'href="(/panel/db/jobs/\d+/[^"]+)"', jobs.text)[:8]:
        print('  href', href)
    for action in actions[:6]:
        # get job page csrf from list
        tok = csrf(jobs.text)
        r = s.post(
            f'{BASE}{action}',
            data={'csrfmiddlewaretoken': tok, 'action': 'run'},
            headers={'Referer': f'{BASE}/panel/db/jobs/'},
            allow_redirects=True,
            timeout=180,
        )
        plain = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', r.text))
        hit = re.findall(r'(запущен|выполнен|ошибк|success|backup|Не найдена|Резервн)[^.]{0,80}', plain, re.I)
        print('  POST', action, '->', r.status_code, hit[:3])


if __name__ == '__main__':
    main()
