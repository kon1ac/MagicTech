"""Единый формат ошибок API + запись ошибок в аудит."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from shop.services.audit import write_audit


def audited_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        response = Response({'detail': exc.messages}, status=status.HTTP_400_BAD_REQUEST)
    elif isinstance(exc, PermissionError):
        response = Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
    else:
        response = exception_handler(exc, context)
    if response is None:
        return None
    request = context.get('request')
    detail = response.data.get('detail') if isinstance(response.data, dict) else response.data
    codes = {400: 'validation_error', 401: 'unauthorized', 403: 'forbidden', 404: 'not_found',
             405: 'method_not_allowed', 409: 'conflict', 429: 'throttled'}
    payload = {
        'error': {
            'code': codes.get(response.status_code, 'error'),
            'status': response.status_code,
            'message': detail if isinstance(detail, str) else (detail[0] if isinstance(detail, list) and detail else 'Ошибка запроса'),
            'details': response.data,
        }
    }
    user = getattr(request, 'user', None) if request else None
    write_audit(
        user=user if getattr(user, 'pk', None) else None,
        object_type='api', object_id=None, action=f'error_{response.status_code}',
        after={'path': request.path if request else '', 'method': request.method if request else '',
               'error': str(payload['error']['message'])[:300]},
        request=request._request if request is not None and hasattr(request, '_request') else None,
    )
    response.data = payload
    return response
