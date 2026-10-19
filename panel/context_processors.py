<<<<<<< HEAD
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
=======
from users.auth_session import get_panel_user
from users.constants import ROLE_LABELS
from users.permissions import PERMISSION_MATRIX, has_permission


def panel_user(request):
    user = get_panel_user(request)
    nav = []
    if user:
        sections = [
            ('dashboard', 'view', 'Обзор', 'panel:dashboard'),
            ('users', 'view', 'Пользователи', 'panel:user_list'),
            ('categories', 'view', 'Категории', 'panel:category_list'),
            ('brands', 'view', 'Бренды', 'panel:brand_list'),
            ('products', 'view', 'Товары', 'panel:product_list'),
            ('promotions', 'view', 'Акции', 'panel:promotion_list'),
            ('orders', 'view', 'Заказы', 'panel:order_list'),
            ('stock', 'view', 'Склад', 'panel:stock_list'),
            ('payments', 'view', 'Платежи', 'panel:payment_list'),
            ('returns', 'view', 'Возвраты', 'panel:return_list'),
            ('reviews', 'view', 'Отзывы', 'panel:review_list'),
            ('audit', 'view', 'Аудит', 'panel:audit_list'),
            ('system', 'view', 'Инфраструктура', 'panel:system_info'),
        ]
        for resource, action, title, url_name in sections:
            if has_permission(user.user_role, resource, action):
                nav.append({'title': title, 'url_name': url_name})
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
    return {
        'panel_user': user,
        'panel_role_label': ROLE_LABELS.get(user.user_role, '') if user else '',
        'panel_nav': nav,
<<<<<<< HEAD
        'panel_settings': user_settings,
=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
        'permission_matrix': PERMISSION_MATRIX,
    }
