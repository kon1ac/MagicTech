from django.contrib.auth.hashers import check_password as auth_check_password
from django.contrib.auth.hashers import make_password
from django.db import models
from django.utils import timezone


class AuthCredentials(models.Model):
    """Учётные данные пользователя (таблица auth_credentials).

    Пароль хранится только как хеш (Argon2/bcrypt) в password_hash — никогда plaintext.
    """

    id_user = models.BigAutoField(primary_key=True)
    email = models.EmailField(max_length=255, unique=True)
    password_hash = models.CharField(max_length=255)
    user_role = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True)
    deactivation_reason = models.CharField(max_length=500, blank=True, default='')
    deactivated_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auth_credentials'
        verbose_name = 'Учётная запись'
        verbose_name_plural = 'Учётные записи'

    def __str__(self):
        return f'{self.email} ({self.user_role})'

    @classmethod
    def get_or_create_ghost(cls):
        """Возвращает системную учётную запись-«призрак».

        Используется для переноса сиротских внешних ключей (Order.id_user,
        Return.id_user) при удалении реального пользователя.
        """
        return cls.objects.get_or_create(
            email='ghost@system.local',
            defaults={
                'password_hash': '',
                'user_role': 'GHOST',
                'is_active': False,
            },
        )

    def transfer_orphans_to_ghost(self):
        """Переносит заказы и возвраты на ghost-учётку перед удалением пользователя.

        Вызывается ДО delete(): Order.id_user и Return.id_user стоят в RESTRICT,
        и именно этот перенос снимает блокировку. updated_at документов не
        сдвигаем — это не редактирование заказа, а служебная перепривязка.
        Возвращает число перенесённых документов.
        """
        from shop.models import Order, Return

        ghost, _ = self.get_or_create_ghost()
        moved = Order.objects.filter(id_user=self).update(id_user=ghost)
        moved += Return.objects.filter(id_user=self).update(id_user=ghost)
        return moved

    # совместимость с DRF: аутентифицированный пользователь API.
    # Property, а не константа True: экземпляр, собранный в памяти (например
    # AuthCredentials() для выравнивания времени ответа), не должен считаться
    # аутентифицированным. Активность учётки здесь не проверяется — её
    # обеспечивает ApiTokenAuthentication и get_current_user.
    is_anonymous = False

    @property
    def is_authenticated(self) -> bool:
        return self.pk is not None

    def set_password(self, raw_password: str) -> None:
        """Хеширует пароль и сохраняет его в password_hash."""
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Проверяет пароль; устаревший хеш прозрачно перехешируется в Argon2."""

        def upgrade(raw):
            self.set_password(raw)
            self.save(update_fields=['password_hash', 'updated_at'])

        return auth_check_password(raw_password, self.password_hash, setter=upgrade)

    def deactivate(self, reason: str, *, save: bool = True) -> None:
        reason = (reason or '').strip()
        if not reason:
            raise ValueError('Укажите основание деактивации.')
        self.is_active = False
        self.deactivation_reason = reason[:500]
        self.deactivated_at = timezone.now()
        if save:
            self.save(update_fields=['is_active', 'deactivation_reason', 'deactivated_at', 'updated_at'])

    def activate(self, *, save: bool = True) -> None:
        self.is_active = True
        self.deactivation_reason = ''
        self.deactivated_at = None
        if save:
            self.save(update_fields=['is_active', 'deactivation_reason', 'deactivated_at', 'updated_at'])


class UserProfiles(models.Model):
    """Профиль пользователя, связь 1:1 с auth_credentials (таблица user_profiles).

    Имя, фамилия, телефон и адрес хранятся в зашифрованном виде (Fernet, prefix enc:v1:).
    Пароль здесь не хранится — только в AuthCredentials.password_hash.
    """

    PII_FIELDS = (
        'profile_first_name',
        'profile_last_name',
        'profile_phone',
        'profile_address',
    )

    id_user = models.OneToOneField(
        AuthCredentials,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='id_user',
        related_name='profile',
    )
    # max_length увеличен под ciphertext Fernet
    profile_first_name = models.CharField(max_length=512, blank=True, null=True)
    profile_last_name = models.CharField(max_length=512, blank=True, null=True)
    profile_phone = models.CharField(max_length=512, blank=True, null=True)
    profile_address = models.TextField(blank=True, null=True)
    profile_avatar_url = models.ImageField(
        upload_to='avatars/',
        max_length=500,
        blank=True,
        null=True,
    )
    pdn_consent_at = models.DateTimeField(blank=True, null=True)
    pdn_consent_version = models.CharField(max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    def __str__(self):
        name = f'{self.get_plain("profile_first_name") or ""} {self.get_plain("profile_last_name") or ""}'.strip()
        return name or str(self.id_user)

    def get_plain(self, field: str) -> str | None:
        from shop.services.crypto import decrypt_text

        return decrypt_text(getattr(self, field))

    def set_plain(self, field: str, value: str | None) -> None:
        from shop.services.crypto import encrypt_text

        setattr(self, field, encrypt_text(value) if value else None)

    @property
    def first_name_display(self) -> str:
        """Только для витрины (покупатель видит своё имя). В панели — cipher_preview."""
        return self.get_plain('profile_first_name') or ''

    @property
    def last_name_display(self) -> str:
        return self.get_plain('profile_last_name') or ''

    @property
    def phone_display(self) -> str:
        return self.get_plain('profile_phone') or ''

    def pii_preview(self, field: str) -> str:
        from shop.services.crypto import cipher_preview

        return cipher_preview(getattr(self, field, None))

    def plain_dict(self) -> dict:
        return {f: self.get_plain(f) for f in self.PII_FIELDS}

    def save(self, *args, **kwargs):
        from shop.services.crypto import ensure_encrypted

        for field in self.PII_FIELDS:
            setattr(self, field, ensure_encrypted(getattr(self, field)))
        super().save(*args, **kwargs)


class UserSettings(models.Model):
    """Пользовательские настройки, хранятся на сервере (таблица user_settings)."""

    THEMES = [('light', 'Светлая'), ('dark', 'Тёмная')]
    LANGUAGES = [('ru', 'Русский'), ('en', 'English')]
    DATE_FORMATS = [
        ('d.m.Y H:i', '31.12.2026 23:59'),
        ('Y-m-d H:i', '2026-12-31 23:59'),
        ('m/d/Y h:i A', '12/31/2026 11:59 PM'),
    ]
    CURRENCY_FORMATS = [('rub_suffix', '1 234,00 ₽'), ('rub_code', 'RUB 1,234.00')]
    PAGE_SIZES = [(10, '10'), (25, '25'), (50, '50'), (100, '100')]

    id_user = models.OneToOneField(
        AuthCredentials,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='id_user',
        related_name='settings',
    )
    theme = models.CharField(max_length=10, choices=THEMES, default='light')
    language = models.CharField(max_length=5, choices=LANGUAGES, default='ru')
    date_format = models.CharField(max_length=20, choices=DATE_FORMATS, default='d.m.Y H:i')
    currency_format = models.CharField(max_length=20, choices=CURRENCY_FORMATS, default='rub_suffix')
    page_size = models.SmallIntegerField(choices=PAGE_SIZES, default=25)
    default_filters = models.JSONField(blank=True, default=dict)
    hotkeys_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_settings'
        verbose_name = 'Настройки пользователя'
        verbose_name_plural = 'Настройки пользователей'

    @classmethod
    def for_user(cls, user):
        settings, _ = cls.objects.get_or_create(id_user=user)
        return settings


class SavedFilter(models.Model):
    """Сохранённые фильтры списков (таблица saved_filters)."""

    id_filter = models.BigAutoField(primary_key=True)
    id_user = models.ForeignKey(
        AuthCredentials, on_delete=models.CASCADE, db_column='id_user', related_name='saved_filters'
    )
    filter_section = models.CharField(max_length=50)
    filter_name = models.CharField(max_length=100)
    filter_query = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'saved_filters'
        ordering = ['filter_name']
        verbose_name = 'Сохранённый фильтр'
        verbose_name_plural = 'Сохранённые фильтры'


class ApiToken(models.Model):
    """API-токен сервисной учётной записи или пользователя (таблица api_tokens).

    В БД хранится только SHA-256 от ключа; сам ключ показывается один раз при выпуске.
    """

    id_token = models.BigAutoField(primary_key=True)
    id_user = models.ForeignKey(
        AuthCredentials, on_delete=models.CASCADE, db_column='id_user', related_name='api_tokens'
    )
    token_name = models.CharField(max_length=100)
    token_prefix = models.CharField(max_length=8)
    token_hash = models.CharField(max_length=64, unique=True)
    token_scopes = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_tokens'
        verbose_name = 'API-токен'
        verbose_name_plural = 'API-токены'

    def __str__(self):
        return f'{self.token_name} ({self.token_prefix}…)'


    @staticmethod
    def hash_key(raw_key: str) -> str:
        import hashlib

        return hashlib.sha256(raw_key.encode()).hexdigest()

    @classmethod
    def issue(cls, user, name: str, scopes: list[str], expires_at=None):
        import secrets

        raw_key = secrets.token_hex(24)
        token = cls.objects.create(
            id_user=user,
            token_name=name,
            token_prefix=raw_key[:8],
            token_hash=cls.hash_key(raw_key),
            token_scopes=scopes,
            expires_at=expires_at,
        )
        return token, raw_key