<p align="center">
  <img src="static/panel/img/logo.svg" width="72" alt="MagicTech"><br>
  <strong style="font-size:1.4rem">MagicTech</strong><br/>
  <em>Интернет-магазин аксессуаров для ПК — единая информационная система</em>
</p>

<p align="center">
  <img alt="Django" src="https://img.shields.io/badge/Django-6.1-092E20?logo=django&logoColor=white"/>
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16+-336791?logo=postgresql&logoColor=white"/>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white"/>
  <img alt="Tests" src="https://img.shields.io/badge/тесты-91_passed-10b981"/>
  <img alt="Version" src="https://img.shields.io/badge/версия-1.0.0-4f46e5"/>
</p>

---

Каталог, корзина с резервированием, атомарное оформление заказа, оплата картой через ЮKassa (имитация веб-хука),
склад со сборкой и списанием, возвраты, отзывы, отчёты с графиками, импорт/экспорт, REST API с OpenAPI,
RBAC на сервере, аудит, бэкапы/restore и инструменты администратора БД.

## Быстрый старт

Требования: Python 3.12+, PostgreSQL 16+ (БД `MagicTech`, пользователь `postgres`, пароль `1` — меняются переменными окружения).

**Linux / macOS**
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
createdb -U postgres MagicTech            # или через pgAdmin
python manage.py migrate
python manage.py seed_magtech             # демо-данные (~60 товаров, ~70 заказов, отзывы, возвраты)
python manage.py ensure_superuser         # суперпользователь Django Admin: Magic / 123
python manage.py runserver
```

**Windows (PowerShell)**
```powershell
python -m venv venv; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate; python manage.py seed_magtech; python manage.py ensure_superuser
python manage.py runserver
```

| URL | Назначение |
|-----|-----------|
| http://127.0.0.1:8000/ | Витрина: каталог, карточка, корзина, оформление, личный кабинет |
| http://127.0.0.1:8000/panel/ | Панель управления (RBAC) |
| http://127.0.0.1:8000/api/docs/ | Swagger UI (OpenAPI 3) · схема: `/api/schema/`, файл `docs/openapi.yaml` |
| http://127.0.0.1:8000/admin/ | Техническая Django Admin — **Magic / 123** |

### Учётные записи (демо)

| Email | Пароль | Роль |
|-------|--------|------|
| `admin@magtech.local` | `Admin123!` | Администратор |
| `db@magtech.local` | `DbAdmin123!` | Администратор БД |
| `merch@magtech.local` | `Merch123!` | Товаровед |
| `acc@magtech.local` | `Acc123!` | Бухгалтер / финансист |
| `picker@magtech.local` | `Pick123!` | Сборщик заказов |
| `buyer@example.com` | `Buyer123!` | Покупатель (витрина) |

Промокоды: `MAGIC500` (−500 ₽ от 5000 ₽), `GAMER15` (−15 % от 2 товаров). Автоакция: −10 % на мыши.
API-токен маркетплейса печатается командой `seed_magtech` (один раз) или выпускается в «Сервисные учётки».

### Переменные окружения

| Переменная | По умолчанию | Назначение |
|-----------|--------------|-----------|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | `MagicTech`, `postgres`, `1`, `localhost`, `5432` | Подключение к PostgreSQL |
| `REDIS_URL` | — | Кеш каталога в Redis (иначе — память процесса) |
| `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` | `1`, dev-ключ, localhost | Боевой режим |
| `YOOKASSA_WEBHOOK_SECRET` | dev-секрет | Подпись веб-хуков ЮKassa (HMAC-SHA256) |
| `MAGTECH_BACKUP_DIR`, `PG_BIN` | `./backups`, PATH | Каталог копий, путь к утилитам PostgreSQL |
| `MAGTECH_SQLITE=1` | — | Только для быстрых проверок без PostgreSQL |

## Что реализовано

| Блок ТЗ | Где |
|---------|-----|
| Каталог: дерево категорий (3 уровня), 50 на страницу, сортировки, динамические фильтры по характеристикам, полнотекстовый поиск с морфологией (PostgreSQL `tsvector` + GIN), карточка с каруселью, отзывами и «с этим покупают», избранное | `store/`, `shop/services/catalog.py`, миграция `shop/0004` |
| Корзина: серверная проверка остатка, резерв на 20 мин, промокоды, пересчёт | `shop/services/cart.py`, `pricing.py` |
| Оформление: атомарно заказ + резерв + платёж + уведомление; статус-флоу NEW → PAID → CONFIRMED → ASSEMBLY → PACKED → COMPLETED / CANCELLED / RETURNED без перескоков | `shop/services/orders.py` |
| Склад: приход со сверкой с накладной, корректировки с подтверждением, сборка с отметкой позиций, списание, возврат на склад при отмене, журнал движений, накладные и ярлыки PDF | `shop/services/stock.py`, панель «Склад», «Сборка» |
| Платежи: ЮKassa (имитация, подписанный веб-хук, идемпотентность), ручное подтверждение, оплата при получении, частичные/полные возвраты с учётом комиссии, импорт выписок CSV/XLSX с автосверкой и журналом несоответствий | `shop/services/payments.py`, `imports.py` |
| Возвраты: NEW → IN_REVIEW → APPROVED/REJECTED → RETURNED_TO_WAREHOUSE → REFUNDED/REPLACED, блокировка после одобрения, аудиторская правка с версией | `shop/services/returns.py` |
| Отзывы: только купившим, премодерация, ответы продавца, атомарный пересчёт рейтинга, вопросы о товаре | `shop/services/reviews.py` |
| RBAC: матрица «роль × объект × действие», проверка в каждом обработчике панели и API (403 + запись в аудит) | `users/permissions.py`, `/panel/users/rbac/` |
| Админ-часть: пользователи и роли, справочники, акции, критические операции, статусы, бэкапы/restore, схема/миграции/индексы/права, регламентные задания, сервисные учётки, характеристики БД, путь к данным, архив, аудит | `panel/` |
| Списки: быстрые и сохранённые фильтры, фильтры по умолчанию, многостолбцовая сортировка (Shift+клик), пагинация, массовые операции с подтверждением | `panel/listing.py` |
| Настройки пользователя на сервере: тема, язык RU/EN, формат даты/валюты, размер страниц, дефолтные фильтры | `users.UserSettings`, `/panel/settings/` |
| Горячие клавиши (12): Ctrl+K, ?, /, Ctrl+N, Ctrl+E, Ctrl+O, S, I, W, P, G | `static/panel/js/panel.js`, `/panel/help/hotkeys/` |
| Импорт товаров/остатков/цен (предпросмотр, сопоставление колонок, всё-или-ничего, отчёт об ошибках по строкам); экспорт каталога CSV/XML(YML), заказов CSV, отчётов CSV/PNG | `shop/services/imports.py`, `exports.py` |
| Отчёты: продажи по периодам, ТОП товаров, финансовый, статусы заказов, остатки и оборачиваемость (Chart.js) | `shop/services/reports.py`, `/panel/reports/` |
| REST API: маркетплейсы, мобильное приложение, callback ЮKassa, внутренняя автоматизация; токены со scope; единый формат ошибок + аудит | `api/`, `docs/openapi.yaml` |
| Безопасность: Argon2, сессии 8 ч + HttpOnly, CSRF, экранирование XSS, ORM-параметры, HTTPS для контура БД, защита от open redirect | `settings.py`, `tests/test_security.py` |

Схема данных — **41 таблица предметной области** (см. `/panel/db/` → «Таблицы» и ER-диаграмму `ERD из pgAdmin.pgerd`).

## Регламентные задания и бэкапы

Планировщик `python manage.py run_scheduled_jobs` запускается раз в минуту (cron — `scripts/crontab.example`,
Windows — Планировщик задач) и выполняет задания по их cron-расписанию из панели «Регламент СУБД»:

| Задание | Расписание |
|---------|-----------|
| Снятие просроченных резервов, отмена неоплаченных заказов | каждые 5 мин |
| Полный бэкап | ежедневно 02:00 |
| Инкрементальный бэкап (транзакционные таблицы) | каждые 4 ч |
| Схема + справочники | еженедельно и при релизе |
| VACUUM ANALYZE | ежедневно 03:30 |
| Ротация копий (хранение 30 дней) | ежедневно 06:00 |
| Проверка restore на тестовом контуре | ежемесячно |
| Архивация заказов старше 365 дней | ежемесячно |

RPO ≤ 15 мин — архив WAL (`scripts/postgresql-wal.conf`, `archive_timeout = 900`); RTO ≤ 1 ч — `scripts/restore.sh|ps1`.
Подробно: `docs/BACKUP.md`.

## Тестирование и замеры

```bash
python manage.py test tests                 # 91 тест: функциональные, интеграционные, безопасность, API
python manage.py generate_products --count 100000
python manage.py benchmark_catalog          # каталог ≤ 300 мс, поиск ≤ 500 мс
python manage.py load_test --orders 50      # 50 параллельных оформлений, проверка отсутствия перепродажи
```
План и протоколы — `docs/TESTING.md`.

## Структура

```
magictech_project/  настройки, маршруты
users/              учётные записи, роли, RBAC, настройки пользователя, API-токены
shop/               модели предметной области, сервисный слой (вся бизнес-логика), команды
panel/              административная часть
store/              публичная витрина и личный кабинет
api/                REST API + OpenAPI
templates/, static/ интерфейс и брендбук
tests/              автотесты
scripts/            бэкапы, restore, роли СУБД, WAL, cron
docs/               OpenAPI, брендбук, регламент бэкапов, тестирование
```

Учебный проект, 4 курс. История изменений — `CHANGELOG.md`.
