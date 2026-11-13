"""Шифрование ПДн at-rest (Fernet). Пароли сюда не входят — только Argon2-хеш.

Ciphertext помечается префиксом enc:v1:, чтобы миграция и чтение отличали
уже зашифрованные значения от legacy plaintext.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from django.conf import settings

logger = logging.getLogger('magictech')

PREFIX = 'enc:v1:'


def _fernet():
    from cryptography.fernet import Fernet

    raw = getattr(settings, 'MAGTECH_PII_ENCRYPTION_KEY', '') or ''
    if raw:
        key = raw.encode() if isinstance(raw, str) else raw
        return Fernet(key)
    # Dev/fallback: стабильный ключ из SECRET_KEY (в production задайте MAGTECH_PII_ENCRYPTION_KEY)
    digest = hashlib.sha256(f'magtech-pii-v1:{settings.SECRET_KEY}'.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted(value: str | None) -> bool:
    return bool(value) and str(value).startswith(PREFIX)


def encrypt_text(plain: str | None) -> str | None:
    if plain is None:
        return None
    text = str(plain)
    if text == '' or is_encrypted(text):
        return text or None
    token = _fernet().encrypt(text.encode('utf-8')).decode('ascii')
    return PREFIX + token


def decrypt_text(value: str | None) -> str | None:
    if value is None or value == '':
        return value
    text = str(value)
    if not is_encrypted(text):
        return text  # legacy plaintext до миграции
    try:
        from cryptography.fernet import InvalidToken

        return _fernet().decrypt(text[len(PREFIX):].encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError, Exception):
        logger.exception('pii decrypt failed')
        return None


def mask_text(value: str | None, *, keep: int = 2) -> str:
    """Маска после расшифровки (только на странице decrypt): Ив** / +7*** / —."""
    plain = decrypt_text(value)
    if not plain:
        return '—'
    if len(plain) <= keep:
        return '*' * len(plain)
    return plain[:keep] + '*' * min(8, len(plain) - keep)


def cipher_preview(value: str | None, *, head: int = 14, tail: int = 4) -> str:
    """Превью ciphertext без расшифровки — для списков панели."""
    if not value:
        return '—'
    text = str(value)
    if is_encrypted(text):
        if len(text) <= head + tail + 1:
            return text
        return f'{text[:head]}…{text[-tail:]}'
    # legacy plaintext до миграции — не светим целиком
    return '⚠ не зашифровано'


def ensure_encrypted(value: str | None) -> str | None:
    """Идемпотентно: plaintext → ciphertext, ciphertext без изменений."""
    return encrypt_text(decrypt_text(value) if value else value)
