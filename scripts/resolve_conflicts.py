"""Разрешение git-конфликтов слияния: оставляем секцию HEAD во всех файлах.

Запуск: python scripts/resolve_conflicts.py
"""

from pathlib import Path

MARKERS = ('<<<<<<< ', '=======', '>>>>>>> ')

# Каталог скриптов лежит в проекте, корень — на уровень выше
ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {'.git', '__pycache__', '.venv', 'venv', 'node_modules',
             '.ruff_cache', 'staticfiles', 'media', 'backups', '.idea'}
TEXT_EXTS = {'.py', '.html', '.css', '.js', '.md', '.txt', '.yaml', '.yml',
             '.json', '.sql', '.ps1', '.sh', '.cfg', '.ini', '.example', '.svg', '.pgerd'}


def resolve(text: str) -> tuple[str, int]:
    """Вернуть текст с оставленными HEAD-секциями и число разрешённых конфликтов."""
    lines = text.splitlines(keepends=True)
    out, count = [], 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('<<<<<<< '):
            count += 1
            head_part = []
            i += 1
            # собираем HEAD-секцию до =======
            while i < len(lines) and not lines[i].startswith('======='):
                head_part.append(lines[i])
                i += 1
            # пропускаем =======
            if i < len(lines):
                i += 1
            # пропускаем inbound-секцию до >>>>>>>
            while i < len(lines) and not lines[i].startswith('>>>>>>> '):
                i += 1
            # пропускаем сам маркер >>>>>>>
            if i < len(lines):
                i += 1
            out.extend(head_part)
        else:
            out.append(line)
            i += 1
    return ''.join(out), count


def main():
    fixed = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() not in TEXT_EXTS and path.name != 'crontab.example':
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        if '<<<<<<< ' not in text:
            continue
        new_text, count = resolve(text)
        path.write_text(new_text, encoding='utf-8', newline='')
        fixed.append((path.relative_to(ROOT), count))
    for rel, n in fixed:
        print(f'{n:>3} conflict(s) resolved: {rel}')
    print(f'\nTotal files fixed: {len(fixed)}')


if __name__ == '__main__':
    main()
