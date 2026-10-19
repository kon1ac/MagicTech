from functools import wraps

<<<<<<< HEAD
from django.core.exceptions import PermissionDenied
=======
from django.contrib import messages
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from users.auth_session import get_panel_user
from users.permissions import has_permission


def panel_login_required(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
<<<<<<< HEAD
        user = get_panel_user(request)
        if not user:
            return redirect(f'/panel/login/?next={request.get_full_path()}')
        request.panel_user = user
=======
        if not get_panel_user(request):
            return redirect('panel:login')
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
        return view_func(request, *args, **kwargs)

    return wrapper


def permission_required(resource: str, action: str):
<<<<<<< HEAD
    """Серверная проверка по матрице RBAC. Нет права → 403 (не просто скрытая кнопка)."""

=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            user = get_panel_user(request)
            if not user:
<<<<<<< HEAD
                return redirect(f'/panel/login/?next={request.get_full_path()}')
            request.panel_user = user
            if not has_permission(user.user_role, resource, action):
                from shop.services.audit import write_audit

                write_audit(user=user, object_type='access', object_id=None, action='denied',
                            after={'resource': resource, 'action': action, 'path': request.path},
                            request=request)
                raise PermissionDenied('Недостаточно прав для этого действия.')
=======
                return redirect('panel:login')
            if not has_permission(user.user_role, resource, action):
                messages.error(request, 'Недостаточно прав для этого действия.')
                return redirect('panel:dashboard')
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
<<<<<<< HEAD


def secure_channel_required(view_func):
    """Доступ к контуру продовой БД — только по HTTPS (в DEBUG допускается localhost)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from django.conf import settings

        if not settings.DEBUG and not request.is_secure():
            raise PermissionDenied('Доступ к контуру БД разрешён только по защищённому каналу (HTTPS).')
        return view_func(request, *args, **kwargs)

    return wrapper
=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
