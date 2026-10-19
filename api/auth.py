"""Авторизация API по токенам (Authorization: Token <ключ>)."""

from django.utils import timezone
from rest_framework import authentication, exceptions, permissions

from users.models import ApiToken


class ApiTokenAuthentication(authentication.BaseAuthentication):
    keyword = 'Token'

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode('latin-1').split()
        if not header or header[0] != self.keyword:
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed('Некорректный заголовок Authorization.')
        token = ApiToken.objects.select_related('id_user').filter(
            token_hash=ApiToken.hash_key(header[1]), is_active=True
        ).first()
        if token is None or not token.id_user.is_active:
            raise exceptions.AuthenticationFailed('Недействительный токен.')
        if token.expires_at and token.expires_at < timezone.now():
            raise exceptions.AuthenticationFailed('Срок действия токена истёк.')
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return token.id_user, token

    def authenticate_header(self, request):
        return self.keyword


class HasScope(permissions.BasePermission):
    """Токен должен иметь нужную область (scope); роль пользователя проверяется отдельно."""

    scope = None

    def has_permission(self, request, view):
        token = request.auth
        scope = getattr(view, 'required_scope', self.scope)
        return bool(token) and scope in (token.token_scopes or [])


class RoleAllowed(permissions.BasePermission):
    """Проверка по матрице RBAC: view.rbac = ('resource', 'action')."""

    def has_permission(self, request, view):
        from users.permissions import has_permission

        rbac = getattr(view, 'rbac', None)
        if rbac is None:
            return True
        user = request.user
        return bool(user) and has_permission(user.user_role, *rbac)
