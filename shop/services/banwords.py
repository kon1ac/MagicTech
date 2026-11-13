"""Фильтр банвордов / оскорблений в текстах отзывов."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

_WORD_RE = re.compile(r'[а-яёa-z0-9]+', re.IGNORECASE)
_DEFAULT_FILE = Path(__file__).resolve().parent.parent / 'data' / 'banwords_ru.txt'


def _normalize(text: str) -> str:
    return (text or '').lower().replace('ё', 'е')


@lru_cache(maxsize=1)
def load_banwords() -> frozenset[str]:
    path = Path(getattr(settings, 'MAGTECH_BANWORDS_FILE', '') or _DEFAULT_FILE)
    words: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.split('#', 1)[0].strip()
            if line:
                words.add(_normalize(line))
    extra = getattr(settings, 'MAGTECH_BANWORDS_EXTRA', '') or ''
    for part in extra.replace(';', ',').split(','):
        part = _normalize(part.strip())
        if part:
            words.add(part)
    return frozenset(words)


def find_banwords(text: str) -> list[str]:
    """Возвращает найденные запрещённые основы (уникальные)."""
    ban = load_banwords()
    if not ban or not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    compact = _normalize(re.sub(r'[\s\-_./\\]+', '', text))
    tokens = _WORD_RE.findall(_normalize(text))
    for token in tokens:
        for root in ban:
            if len(root) >= 3 and root in token and root not in seen:
                seen.add(root)
                found.append(root)
    # склейка «б л я д ь» / «хуй»
    for root in ban:
        if len(root) >= 3 and root in compact and root not in seen:
            seen.add(root)
            found.append(root)
    return found


def validate_no_banwords(text: str) -> None:
    hits = find_banwords(text)
    if hits:
        raise ValidationError(
            'Отзыв нельзя отправить: текст содержит недопустимые слова или оскорбления. '
            'Уберите нецензурную лексику и повторите попытку.'
        )
