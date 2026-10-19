"""Запись в журнал аудита."""

from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest

from shop.models import AuditLog
from users.models import AuthCredentials


def _client_meta(request: HttpRequest | None) -> tuple[str | None, str | None]:
    if not request:
        return None, None
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get(
        'REMOTE_ADDR'
    )
    ua = request.META.get('HTTP_USER_AGENT', '')[:500]
    return ip or None, ua or None


def write_audit(
    *,
    user: AuthCredentials | None,
    object_type: str,
    object_id: int | None,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditLog:
    ip, ua = _client_meta(request)
    payload_before = json.dumps(before, ensure_ascii=False) if before is not None else None
    payload_after = json.dumps(after, ensure_ascii=False) if after is not None else None
    return AuditLog.objects.create(
        id_user=user,
        audit_object_type=object_type,
        object_id=object_id,
        audit_action=action,
        audit_before=payload_before,
        audit_after=payload_after,
        audit_ip=ip,
        audit_user_agent=ua,
    )
