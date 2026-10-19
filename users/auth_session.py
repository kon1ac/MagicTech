"""Сессионная аутентификация панели управления (AuthCredentials)."""

from __future__ import annotations

from django.http import HttpRequest

from users.constants import STAFF_ROLES
from users.models import AuthCredentials

SESSION_USER_KEY = 'magtech_user_id'


def login_user(request: HttpRequest, user: AuthCredentials) -> None:
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
        return None
    return user


def authenticate_credentials(email: str, password: str) -> AuthCredentials | None:
    try:
        user = AuthCredentials.objects.get(email__iexact=email.strip(), is_active=True)
    except AuthCredentials.DoesNotExist:
        return None
    if user.user_role not in STAFF_ROLES:
        return None
    if not user.check_password(password):
        return None
    return user
