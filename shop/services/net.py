"""Безопасное определение IP-адреса клиента.

Используется в audit.py, login_guard.py и api/errors.py, чтобы не
допускать DataError в audit_log.audit_ip и не обходить XFF-лимиты.
"""

from __future__ import annotations

import ipaddress

from django.conf import settings


def client_ip(request) -> str | None:
    """Возвращает валидный IP или None.

    Если MAGTECH_TRUST_XFF=True — первый валидный из X-Forwarded-For.
    Иначе — всегда REMOTE_ADDR (за ним должен стоять прокси, который
    отчищает XFF).
    """
    if getattr(settings, 'MAGTECH_TRUST_XFF', False):
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        for part in xff.split(','):
            addr = part.strip()
            if addr:
                try:
                    ipaddress.ip_address(addr)
                    return addr
                except ValueError:
                    continue

    addr = request.META.get('REMOTE_ADDR', '')
    if addr:
        try:
            ipaddress.ip_address(addr)
            return addr
        except ValueError:
            pass
    return None
