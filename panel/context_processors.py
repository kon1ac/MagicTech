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
    return {
        'panel_user': user,
        'panel_role_label': ROLE_LABELS.get(user.user_role, '') if user else '',
        'panel_nav': nav,
        'permission_matrix': PERMISSION_MATRIX,
    }
