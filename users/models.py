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

    def set_password(self, raw_password: str) -> None:
        """Хеширует пароль и сохраняет его в password_hash."""
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Проверяет соответствие пароля сохранённому хешу."""
        return auth_check_password(raw_password, self.password_hash)


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
