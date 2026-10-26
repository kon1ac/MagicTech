"""Защита от перебора пароля на страницах входа.

Счётчики неудачных попыток живут в кэше (LocMem или Redis) и считаются
двумерно: по IP клиента и по email-аккаунту. Превышение лимита вешает
блокировку на окно MAGTECH_LOGIN_FAIL_WINDOW_SECONDS.

Лимиты раздельные: панель — жёстче (там доступ к администрированию),
витрина — мягче, чтобы случайный покупатель не заблокировал себя надолго.
"""

from __future__ import annotations

import time

from django.conf import settings
from django.core.cache import cache


def _client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (xff.split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')) or 'unknown'


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

    def _identifiers(self, email: str, request) -> list[str]:
        idents = [f'ip:{_client_ip(request)}']
        email = (email or '').strip().lower()
        if email:
            idents.append(f'email:{email}')
        return idents

    def register_fail(self, email: str, request) -> None:
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

    def lockout_for(self, request, email: str = '') -> int | None:
        """Секунд до разблокировки; None, если вход не заблокирован."""
        for ident in self._identifiers(email, request):
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
