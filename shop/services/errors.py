"""Общие кортежи/списки исключений для единообразной обработки."""

from __future__ import annotations

from django.db import IntegrityError
from django.db.models.deletion import ProtectedError, RestrictedError

PROTECTED_ERRORS = (ProtectedError, RestrictedError)
__all__ = ['PROTECTED_ERRORS', 'IntegrityError']
