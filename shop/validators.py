"""Общие валидаторы загружаемых файлов.

Живут отдельно от форм: их используют и панель, и витрина, и импорт,
поэтому зависимость store → panel здесь была бы лишней.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = ('.csv', '.txt', '.xlsx', '.xlsm')


def validate_upload(file):
    """Импорт данных: ограничение размера и расширения.

    Одна функция на все формы — иначе новая форма загрузки легко остаётся
    без ограничения размера (так было со StatementUploadForm).
    """
    if file.size > MAX_UPLOAD_BYTES:
        raise ValidationError('Файл больше 30 МБ.')
    if not file.name.lower().endswith(ALLOWED_UPLOAD_SUFFIXES):
        raise ValidationError('Допустимы файлы .csv, .txt или .xlsx.')
    return file


def validate_image(file):
    """Фото товара, отзыва или аватара — ограничение размера."""
    limit_mb = getattr(settings, 'MAGTECH_MAX_IMAGE_MB', 5)
    if file.size > limit_mb * 1024 * 1024:
        raise ValidationError(f'Изображение больше {limit_mb} МБ.')
    return file
