"""Перевод интерфейса панели (RU/EN). Язык хранится в настройках пользователя на сервере."""

EN = {
    'Обзор': 'Overview', 'Пользователи': 'Users', 'Категории': 'Categories', 'Бренды': 'Brands',
    'Характеристики': 'Attributes', 'Справочники': 'References', 'Товары': 'Products', 'Акции': 'Promotions',
    'Заказы': 'Orders', 'Склад': 'Warehouse', 'Сборка': 'Picking', 'Платежи': 'Payments',
    'Выписки': 'Bank statements', 'Возвраты': 'Returns', 'Отзывы': 'Reviews', 'Отчёты': 'Reports',
    'Импорт / экспорт': 'Import / export', 'Аудит': 'Audit', 'База данных': 'Database',
    'Бэкапы': 'Backups', 'Регламент СУБД': 'DB jobs', 'Сервисные учётки': 'Service accounts',
    'Архив': 'Archive', 'Настройки': 'Settings', 'Выйти': 'Log out', 'Сохранить': 'Save',
    'Фильтр': 'Filter', 'Сбросить': 'Reset', 'Поиск': 'Search', 'Каталог': 'Catalog',
    'Финансы': 'Finance', 'Аналитика': 'Analytics', 'Инфраструктура': 'Infrastructure',
    'Сохранённые фильтры': 'Saved filters', 'Сохранить фильтр': 'Save filter', 'Применить': 'Apply',
    'Массовое действие': 'Bulk action', 'Подтверждаю операцию': 'I confirm this operation',
    'Журнал изменений': 'Change log', 'Связанные объекты': 'Related objects', 'Витрина': 'Storefront',
    'Горячие клавиши': 'Hotkeys', 'Брендбук': 'Brand book',
    'Поиск по SKU / названию (Alt+K)': 'Search SKU / name (Alt+K)',
}


def translate(text: str, language: str) -> str:
    if language == 'en':
        return EN.get(text, text)
    return text
