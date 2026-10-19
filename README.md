<p align="center">
  <strong style="font-size:1.4rem">MagicTech</strong><br/>
  <em>Интернет-магазин аксессуаров для ПК — единая информационная система</em>
</p>

<p align="center">
  <img alt="Django" src="https://img.shields.io/badge/Django-6.1-092E20?logo=django&logoColor=white"/>
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16+-336791?logo=postgresql&logoColor=white"/>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white"/>
  <img alt="Status" src="https://img.shields.io/badge/Статус-в_разработке-4f46e5"/>
</p>

---

## О проекте

**MagicTech** — учебно-прикладной проект курсовой работы: интернет-магазин аксессуаров для ПК (клавиатуры, мыши, наушники, кабели, кресла и др.) с централизованным каталогом, складом, заказами, биллингом и отзывами.

Целевая ИС закрывает хаос «Excel + CRM + бумажный склад»: единые остатки, роли, аудит критических операций и регламенты резервного копирования.

## Что уже реализовано

### Модель данных (PostgreSQL)

| Блок | Сущности |
|------|----------|
| Каталог | `categories`, `brands`, `products`, `prices`, `promotions` (+ связи с категориями/брендами/товарами) |
| Заказы | `carts`, `cart_items`, `orders`, `order_items`, `order_promotions` |
| Склад | `stock` (остаток, резерв, история движений JSON) |
| Финансы | `payments`, `returns`, `return_items` |
| Клиенты | `auth_credentials`, `user_profiles` |
| Репутация | `reviews` (отзывы / вопросы, модерация) |
| Аудит | `audit_log` (действие, до/после, IP, User-Agent) |

> **≥ 20 таблиц** в предметной области, миграции Django (`shop`, `users`).

### Панель управления `/panel/` (основной фокус)

Адаптивный UI (mobile / tablet / desktop), брендбук MagicTech (Indigo + Cyan, шрифты Manrope / JetBrains Mono):

| Раздел | Возможности |
|--------|-------------|
| **Обзор** | KPI: товары, заказы в работе, выручка, отзывы на модерации |
| **Пользователи** | CRUD staff-аккаунтов, назначение ролей |
| **Справочники** | Категории, бренды, товары, акции |
| **Заказы** | Список, фильтры, карточка, **регламент смены статусов** |
| **Склад** | Остатки/резервы, **корректировка с подтверждением**, сборка и списание |
| **Платежи / возвраты** | Просмотр реестров |
| **Отзывы** | Модерация (`pending` → `approved` / `rejected`) |
| **Аудит** | Журнал + **экспорт CSV** |
| **Инфраструктура** | Параметры БД, путь к медиа, регламент бэкапов (RPO/RTO) |

Дополнительно: **Django Admin** (`/admin/`) — технический доступ ко всем моделям.

### RBAC (серверная авторизация)

Роли: `ADMIN`, `DB_ADMIN`, `MERCHANDISER`, `ACCOUNTANT`, `PICKER`, `CUSTOMER`.

Матрица «роль × объект × действие» — `users/permissions.py`, проверка в декораторах `@permission_required` (не только скрытие кнопок в UI).

### Бизнес-логика (сервер)

- **Статусы заказов** — только разрешённые переходы (`users/constants.py` → `shop/services/orders.py`).
- **Отмена заказа** — снятие резерва, запись в аудит, подтверждение для критической операции.
- **Склад** — запрет отрицательного остатка, корректировки и списания в транзакциях + аудит.
- **Пароли** — хеширование Django (`make_password` / `check_password`).

### UX

- Светлая / тёмная тема (localStorage)
- Горячие клавиши: `Ctrl+K`, `/`, `?`, `Ctrl+N`, `Ctrl+O`, и др. — см. `/panel/help/hotkeys/`

## Что запланировано дальше

- Публичная витрина (каталог, корзина, ЮKassa, ЛК покупателя)
- REST API + OpenAPI
- Redis-кеш каталога, полнотекстовый поиск
- Импорт CSV / отчёты с графиками
- Unit / integration / нагрузочные тесты, CI

---

## Быстрый старт

### Требования

- Python 3.12+
- PostgreSQL (БД `MagicTech`, пользователь `postgres` — см. `magictech_project/settings.py`)

### Установка

```powershell
cd MagicTech
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Миграции и демо-данные

```powershell
python manage.py migrate
python manage.py seed_magtech
```

### Запуск

```powershell
python manage.py runserver
```

| URL | Назначение |
|-----|------------|
| http://127.0.0.1:8000/panel/ | Панель управления |
| http://127.0.0.1:8000/admin/ | Django Admin |

### Демо-учётки панели

| Email | Пароль | Роль |
|-------|--------|------|
| `admin@magtech.local` | `Admin123!` | Администратор |
| `db@magtech.local` | `DbAdmin123!` | Администратор БД |
| `merch@magtech.local` | `Merch123!` | Товаровед |
| `acc@magtech.local` | `Acc123!` | Бухгалтер |
| `picker@magtech.local` | `Pick123!` | Сборщик |

Покупатель для демо-заказа: `buyer@example.com` / `Buyer123!`

---

## Структура репозитория

```
MagicTech/
├── magictech_project/     # settings, urls
├── users/                 # auth_credentials, RBAC, роли
├── shop/                  # доменные модели и сервисы
├── panel/                 # админ-панель (views, forms, RBAC)
├── templates/panel/       # HTML-шаблоны
├── static/panel/          # CSS/JS, брендбук
├── manage.py
└── requirements.txt
```

## Регламент резервного копирования (целевой)

| Тип | Периодичность |
|-----|----------------|
| Полный бэкап БД | Ежедневно, ночное окно |
| Инкрементальный | Каждые 4 часа |
| Конфигурации / справочники | При релизе / изменении схемы |
| Хранение | ≥ 30 дней |
| Проверка restore | ≥ 1 раз в месяц на тестовом контуре |
| RPO / RTO | ≤ 15 мин / ≤ 1 ч |

Описание отображается в панели: **Инфраструктура**.

## Лицензия и авторство

Учебный проект, 4 курс. Репозиторий: Git + осмысленные коммиты, README и ПЗ обновляются по мере реализации функций.

---

<p align="center"><sub>MagicTech · каталог · корзина · заказы · склад · биллинг · отзывы</sub></p>
