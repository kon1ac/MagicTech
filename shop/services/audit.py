"""Запись в журнал аудита."""

from __future__ import annotations

import json
from typing import Any

<<<<<<< HEAD
from django.core.serializers.json import DjangoJSONEncoder
=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
from django.http import HttpRequest

from shop.models import AuditLog
from users.models import AuthCredentials


<<<<<<< HEAD
def client_meta(request: HttpRequest | None) -> tuple[str | None, str | None]:
=======
def _client_meta(request: HttpRequest | None) -> tuple[str | None, str | None]:
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
    if not request:
        return None, None
    ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get(
        'REMOTE_ADDR'
    )
    ua = request.META.get('HTTP_USER_AGENT', '')[:500]
    return ip or None, ua or None


<<<<<<< HEAD
def _dump(payload: dict[str, Any] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False, cls=DjangoJSONEncoder)


=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
def write_audit(
    *,
    user: AuthCredentials | None,
    object_type: str,
    object_id: int | None,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
<<<<<<< HEAD
    reason: str | None = None,
    request: HttpRequest | None = None,
) -> AuditLog:
    ip, ua = client_meta(request)
    return AuditLog.objects.create(
        id_user=user if isinstance(user, AuthCredentials) else None,
        audit_object_type=object_type,
        object_id=object_id,
        audit_action=action,
        audit_before=_dump(before),
        audit_after=_dump(after),
        audit_reason=(reason or None) and reason[:500],
        audit_ip=ip,
        audit_user_agent=ua,
    )


def object_history(object_type: str, object_id: int, limit: int = 50):
    return (
        AuditLog.objects.select_related('id_user')
        .filter(audit_object_type=object_type, object_id=object_id)
        .order_by('-created_at')[:limit]
    )
=======
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
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
