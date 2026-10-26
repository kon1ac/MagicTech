from panel.i18n import translate
from users.auth_session import get_panel_user
from users.constants import ROLE_LABELS
from users.models import UserSettings
from users.permissions import PERMISSION_MATRIX, has_permission

NAV = [
    ('Обзор', [
        ('dashboard', 'view', 'Обзор', 'panel:dashboard'),
        ('reports', 'view', 'Отчёты', 'panel:reports'),
    ]),
    ('Каталог', [
        ('products', 'view', 'Товары', 'panel:product_list'),
        ('categories', 'view', 'Категории', 'panel:category_list'),
        ('brands', 'view', 'Бренды', 'panel:brand_list'),
        ('characteristics', 'view', 'Характеристики', 'panel:characteristic_list'),
        ('promotions', 'view', 'Акции', 'panel:promotion_list'),
        ('reviews', 'view', 'Отзывы', 'panel:review_list'),
        ('products', 'import', 'Импорт / экспорт', 'panel:io_index'),
    ]),
    ('Заказы', [
        ('orders', 'view', 'Заказы', 'panel:order_list'),
        ('stock', 'view', 'Склад', 'panel:stock_list'),
        ('stock', 'pick', 'Сборка', 'panel:pick_tasks'),
    ]),
    ('Финансы', [
        ('payments', 'view', 'Платежи', 'panel:payment_list'),
        ('payments', 'import', 'Выписки', 'panel:statement_list'),
        ('returns', 'view', 'Возвраты', 'panel:return_list'),
    ]),
    ('Инфраструктура', [
        ('users', 'view', 'Пользователи', 'panel:user_list'),
        ('references', 'view', 'Справочники', 'panel:references'),
        ('db', 'view', 'База данных', 'panel:db_overview'),
        ('db', 'backup', 'Бэкапы', 'panel:db_backups'),
        ('db', 'jobs', 'Регламент СУБД', 'panel:db_jobs'),
        ('db', 'service_accounts', 'Сервисные учётки', 'panel:db_service_accounts'),
        ('archive', 'view', 'Архив', 'panel:archive'),
        ('audit', 'view', 'Аудит', 'panel:audit_list'),
    ]),
]

# Хоткеи, порождающие переход: клавиша -> URL. Единый источник истины для
# panel.js и страницы справки — чтобы нигде не расходился список клавиш.
HOTKEY_ROUTES = {
    'alt+o': '/panel/orders/',
    'alt+n': '/panel/products/new/',
    'alt+g': '/panel/',
    'alt+e': '/panel/products/',        # префикс: конкретный id подставляет JS
    'i': '/panel/stock/receipt/',
    'w': '/panel/picking/',
}

# Какое право нужно для перехода по URL-префиксу. Порядок важен: проверяется
# первый совпавший префикс, поэтому частные пути стоят раньше общих
# ('/panel/products/new/' раньше '/panel/products/'). Синхронизировано с
# декораторами @permission_required в panel/views*.py — сама защита на
# сервере, здесь только «не водить пользователя в заведомый 403».
URL_GUARDS = [
    ('/panel/products/new/', 'products', 'create'),
    ('/panel/products/', 'products', 'update'),
    ('/panel/orders/', 'orders', 'view'),
    ('/panel/stock/receipt/', 'stock', 'receipt'),
    ('/panel/picking/', 'stock', 'pick'),
    ('/panel/users/', 'users', 'view'),
    ('/panel/', 'dashboard', 'view'),
]


def url_guards_for(role: str) -> list[list]:
    """[[префикс, доступна_ли], ...] в порядке URL_GUARDS — для проверки на клиенте."""
    return [[prefix, has_permission(role, resource, action)] for prefix, resource, action in URL_GUARDS]


def hotkeys_for(role: str) -> dict:
    """Клавиша -> bool: какие переходы разрешены этой роли (для страницы справки).

    Ключи с модификатором приводятся к виду 'alt_o': Django-шаблон не умеет
    доставать из словаря ключи с '+'.
    """
    result = {}
    for key, url in HOTKEY_ROUTES.items():
        result[key.replace('+', '_')] = next(
            (has_permission(role, r, a) for prefix, r, a in URL_GUARDS if url.startswith(prefix)),
            True,
        )
    return result


def panel_user(request):
    if not request.path.startswith('/panel'):
        return {}
    user = get_panel_user(request)
    nav = []
    user_settings = None
    if user:
        user_settings = UserSettings.for_user(user)
        lang = user_settings.language
        for group, items in NAV:
            links = [
                {'title': translate(title, lang), 'url_name': url_name}
                for resource, action, title, url_name in items
                if has_permission(user.user_role, resource, action)
            ]
            if links:
                nav.append({'title': translate(group, lang), 'links': links})
    return {
        'panel_user': user,
        'panel_role_label': ROLE_LABELS.get(user.user_role, '') if user else '',
        'panel_nav': nav,
        'panel_settings': user_settings,
        'permission_matrix': PERMISSION_MATRIX,
        # доступность переходов по хоткеям для текущей роли (клиент + страница справки)
        'hotkey_guards': url_guards_for(user.user_role) if user else [],
        'hotkeys_allowed': hotkeys_for(user.user_role) if user else {},
    }
