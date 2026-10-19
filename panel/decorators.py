from functools import wraps

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from users.auth_session import get_panel_user
from users.permissions import has_permission


def panel_login_required(view_func):
    @wraps(view_func)
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not get_panel_user(request):
            return redirect('panel:login')
        return view_func(request, *args, **kwargs)

    return wrapper


def permission_required(resource: str, action: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            user = get_panel_user(request)
            if not user:
                return redirect('panel:login')
            if not has_permission(user.user_role, resource, action):
                messages.error(request, 'Недостаточно прав для этого действия.')
                return redirect('panel:dashboard')
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
