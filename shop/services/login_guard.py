"""Защита от перебора пароля на страницах входа.

Счётчики неудачных попыток живут в кэше (LocMem или Redis) и считаются
двумерно: по IP клиента и по email-аккаунту. Превышение лимита вешает
временную блокировку на окно MAGTECH_LOGIN_FAIL_WINDOW_SECONDS.

После MAGTECH_LOGIN_AUTO_BAN_AFTER неудач по email учётная запись
деактивируется с основанием (постоянный бан до ручной разблокировки админом).
Работает и для уже деактивированных: попытки всё равно копятся и удлиняют lockout,
без раскрытия статуса учётки в ответе.
"""

from __future__ import annotations

import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from shop.services.net import client_ip

logger = logging.getLogger('magictech')


def _client_ip(request) -> str:
    """Валидный IP либо 'unknown' — ключ счётчика не должен зависеть от XFF-мусора."""
    return client_ip(request) or 'unknown'


class LoginGuard:
    """Счётчик неудачных входов для одной области (панель или витрина)."""

    def __init__(self, scope: str, max_setting: str):
        self.scope = scope
        self.max_setting = max_setting

    @property
    def max_attempts(self) -> int:
        # настройки читаем лениво — override_settings в тестах должен работать
        return getattr(settings, self.max_setting, 10)

    @property
    def window(self) -> int:
        return getattr(settings, 'MAGTECH_LOGIN_FAIL_WINDOW_SECONDS', 900)

    @property
    def auto_ban_after(self) -> int:
        return int(getattr(settings, 'MAGTECH_LOGIN_AUTO_BAN_AFTER', 20))

    def _identifiers(self, email: str, request) -> list[str]:
        idents = [f'ip:{_client_ip(request)}']
        email = (email or '').strip().lower()
        if email:
            idents.append(f'email:{email}')
        return idents

    def register_fail(self, email: str, request) -> None:
        email_norm = (email or '').strip().lower()
        email_fails = 0
        for ident in self._identifiers(email, request):
            key = f'login:{self.scope}:fail:{ident}'
            try:
                fails = cache.incr(key)
            except ValueError:
                # add (а не set) — чтобы окно отсчитывалось от первой попытки
                cache.add(key, 1, self.window)
                fails = 1
            if fails >= self.max_attempts:
                cache.set(f'login:{self.scope}:lock:{ident}', time.time() + self.window, self.window)
            if ident.startswith('email:'):
                email_fails = fails
        if email_norm and email_fails >= self.auto_ban_after:
            self._auto_ban(email_norm, request, email_fails)

    def _auto_ban(self, email: str, request, fails: int) -> None:
        from shop.services.audit import write_audit
        from users.models import AuthCredentials

        ban_key = f'login:{self.scope}:autoban:{email}'
        if cache.get(ban_key):
            return
        user = AuthCredentials.objects.filter(email__iexact=email).first()
        if user is None or user.user_role == 'GHOST':
            return
        reason = (
            f'Автоблокировка после {fails} неудачных попыток входа '
            f'({self.scope}, окно {self.window} с)'
        )
        try:
            if user.is_active:
                user.deactivate(reason)
            else:
                # уже неактивен — фиксируем основание, если пусто
                if not user.deactivation_reason:
                    user.deactivation_reason = reason
                    user.deactivated_at = user.deactivated_at or timezone.now()
                    user.save(update_fields=['deactivation_reason', 'deactivated_at', 'updated_at'])
            write_audit(
                user=None, object_type='user', object_id=user.pk, action='auto_ban',
                after={'email': email, 'fails': fails, 'scope': self.scope},
                reason=reason, request=request,
            )
            cache.set(ban_key, 1, self.window)
            logger.warning('login auto-ban email=%s scope=%s fails=%s', email, self.scope, fails)
        except Exception:
            logger.exception('auto_ban failed for %s', email)

    def lockout_for(self, request, email: str) -> int | None:
        """Секунд до разблокировки; None, если вход не заблокирован."""
        email = (email or '').strip().lower()
        idents = self._identifiers(email, request)
        for ident in idents:
            until = cache.get(f'login:{self.scope}:lock:{ident}')
            if until:
                left = int(until - time.time())
                if left > 0:
                    return left
        return None

    def reset(self, email: str, request) -> None:
        """Успешный вход обнуляет счётчики — накопленные «почти-угадывания» не копят блокировку."""
        for ident in self._identifiers(email, request):
            cache.delete(f'login:{self.scope}:fail:{ident}')
            cache.delete(f'login:{self.scope}:lock:{ident}')


login_guard = LoginGuard('panel', 'MAGTECH_PANEL_LOGIN_MAX_ATTEMPTS')
store_login_guard = LoginGuard('store', 'MAGTECH_STORE_LOGIN_MAX_ATTEMPTS')
