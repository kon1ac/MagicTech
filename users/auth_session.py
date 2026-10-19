<<<<<<< HEAD
"""Сессионная аутентификация (AuthCredentials) для панели и витрины."""
=======
"""Сессионная аутентификация панели управления (AuthCredentials)."""
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719

from __future__ import annotations

from django.http import HttpRequest

from users.constants import STAFF_ROLES
from users.models import AuthCredentials

SESSION_USER_KEY = 'magtech_user_id'


def login_user(request: HttpRequest, user: AuthCredentials) -> None:
<<<<<<< HEAD
    request.session.cycle_key()  # защита от фиксации сессии
    request.session[SESSION_USER_KEY] = user.id_user


def logout_user(request: HttpRequest) -> None:
    request.session.flush()


def get_current_user(request: HttpRequest) -> AuthCredentials | None:
    cached = getattr(request, '_magtech_user', False)
    if cached is not False:
        return cached
    user = None
    user_id = request.session.get(SESSION_USER_KEY)
    if user_id:
        user = AuthCredentials.objects.filter(pk=user_id, is_active=True).first()
    request._magtech_user = user
    return user


def get_panel_user(request: HttpRequest) -> AuthCredentials | None:
    user = get_current_user(request)
    if user is None or user.user_role not in STAFF_ROLES:
=======
    request.session[SESSION_USER_KEY] = user.id_user
    request.session.cycle_key()


def logout_user(request: HttpRequest) -> None:
    request.session.pop(SESSION_USER_KEY, None)


def get_panel_user(request: HttpRequest) -> AuthCredentials | None:
    user_id = request.session.get(SESSION_USER_KEY)
    if not user_id:
        return None
    try:
        user = AuthCredentials.objects.get(pk=user_id, is_active=True)
    except AuthCredentials.DoesNotExist:
        return None
    if user.user_role not in STAFF_ROLES:
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
        return None
    return user


<<<<<<< HEAD
def authenticate_credentials(email: str, password: str, *, staff_only: bool = True) -> AuthCredentials | None:
    try:
        user = AuthCredentials.objects.get(email__iexact=email.strip(), is_active=True)
    except AuthCredentials.DoesNotExist:
        AuthCredentials().set_password(password)  # выравнивание времени ответа
        return None
    if staff_only and user.user_role not in STAFF_ROLES:
=======
def authenticate_credentials(email: str, password: str) -> AuthCredentials | None:
    try:
        user = AuthCredentials.objects.get(email__iexact=email.strip(), is_active=True)
    except AuthCredentials.DoesNotExist:
        return None
    if user.user_role not in STAFF_ROLES:
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
        return None
    if not user.check_password(password):
        return None
    return user
