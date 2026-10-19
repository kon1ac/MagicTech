from django.contrib.auth.hashers import check_password as auth_check_password
from django.contrib.auth.hashers import make_password
from django.db import models


class AuthCredentials(models.Model):
    """Учётные данные пользователя (таблица auth_credentials)."""

    id_user = models.BigAutoField(primary_key=True)
    email = models.EmailField(max_length=255, unique=True)
    password_hash = models.CharField(max_length=255)
    user_role = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'auth_credentials'
        verbose_name = 'Учётная запись'
        verbose_name_plural = 'Учётные записи'

    def __str__(self):
        return f'{self.email} ({self.user_role})'

<<<<<<< HEAD
    # совместимость с DRF: аутентифицированный пользователь API
    is_authenticated = True
    is_anonymous = False

=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
    def set_password(self, raw_password: str) -> None:
        """Хеширует пароль и сохраняет его в password_hash."""
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
<<<<<<< HEAD
        """Проверяет пароль; устаревший хеш прозрачно перехешируется в Argon2."""

        def upgrade(raw):
            self.set_password(raw)
            self.save(update_fields=['password_hash', 'updated_at'])

        return auth_check_password(raw_password, self.password_hash, setter=upgrade)
=======
        """Проверяет соответствие пароля сохранённому хешу."""
        return auth_check_password(raw_password, self.password_hash)
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719


class UserProfiles(models.Model):
    """Профиль пользователя, связь 1:1 с auth_credentials (таблица user_profiles)."""

    id_user = models.OneToOneField(
        AuthCredentials,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='id_user',
        related_name='profile',
    )
    profile_first_name = models.CharField(max_length=100, blank=True, null=True)
    profile_last_name = models.CharField(max_length=100, blank=True, null=True)
    profile_phone = models.CharField(max_length=30, blank=True, null=True)
    profile_address = models.TextField(blank=True, null=True)
    profile_avatar_url = models.ImageField(
        upload_to='avatars/',
        max_length=500,
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    def __str__(self):
        name = f'{self.profile_first_name or ""} {self.profile_last_name or ""}'.strip()
        return name or str(self.id_user)
<<<<<<< HEAD


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
=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
