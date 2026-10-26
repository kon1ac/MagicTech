"""Матрица «Роль × Объект × Действие» — серверная авторизация панели и API."""

from users.constants import (
    ROLE_ACCOUNTANT,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_DB_ADMIN,
    ROLE_MERCHANDISER,
    ROLE_PICKER,
)

ADMINS = {ROLE_ADMIN, ROLE_DB_ADMIN}
ALL_STAFF = {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER, ROLE_ACCOUNTANT, ROLE_PICKER}

# resource -> action -> roles
PERMISSION_MATRIX = {
    'dashboard': {
        'view': ALL_STAFF,
    },
    'users': {
        'view': ADMINS,
        'create': ADMINS,
        'update': ADMINS,
        'delete': ADMINS,
        'change_role': ADMINS,
    },
    'categories': {
        'view': ADMINS | {ROLE_MERCHANDISER},
        'create': ADMINS | {ROLE_MERCHANDISER},
        'update': ADMINS | {ROLE_MERCHANDISER},
        'delete': ADMINS,
    },
    'brands': {
        'view': ADMINS | {ROLE_MERCHANDISER},
        'create': ADMINS | {ROLE_MERCHANDISER},
        'update': ADMINS | {ROLE_MERCHANDISER},
        'delete': ADMINS,
    },
    'characteristics': {
        'view': ADMINS | {ROLE_MERCHANDISER},
        'create': ADMINS | {ROLE_MERCHANDISER},
        'update': ADMINS | {ROLE_MERCHANDISER},
        'delete': ADMINS,
    },
    'references': {
        'view': ADMINS,
        'update': ADMINS,
    },
    'products': {
        'view': ADMINS | {ROLE_MERCHANDISER, ROLE_PICKER},
        'create': ADMINS | {ROLE_MERCHANDISER},
        'update': ADMINS | {ROLE_MERCHANDISER},
        'delete': ADMINS,
        'import': ADMINS | {ROLE_MERCHANDISER},
        'export': ADMINS | {ROLE_MERCHANDISER},
    },
    'prices': {
        'view': ADMINS | {ROLE_MERCHANDISER, ROLE_ACCOUNTANT},
        'update': ADMINS | {ROLE_MERCHANDISER},
        'import': ADMINS | {ROLE_MERCHANDISER},
    },
    'promotions': {
        'view': ADMINS | {ROLE_MERCHANDISER},
        'create': ADMINS,
        'update': ADMINS,
        'delete': ADMINS,
    },
    'orders': {
        'view': ADMINS | {ROLE_ACCOUNTANT, ROLE_PICKER},
        'update_status': ADMINS,
        'cancel_critical': ADMINS,
        'bulk': ADMINS,
        'export': ADMINS | {ROLE_ACCOUNTANT},
        'mark_cod_paid': ADMINS,
    },
    'stock': {
        'view': ADMINS | {ROLE_MERCHANDISER, ROLE_PICKER},
        'adjust_critical': ADMINS,
        'receipt': ADMINS | {ROLE_PICKER},
        'pick': ADMINS | {ROLE_PICKER},
        'print': ADMINS | {ROLE_PICKER},
        'import': ADMINS,
    },
    'payments': {
        'view': ADMINS | {ROLE_ACCOUNTANT},
        'update': ADMINS | {ROLE_ACCOUNTANT},
        'refund': ADMINS | {ROLE_ACCOUNTANT},
        'import': ADMINS | {ROLE_ACCOUNTANT},
    },
    'returns': {
        'view': ADMINS | {ROLE_ACCOUNTANT},
        'create': ADMINS,
        'update': ADMINS | {ROLE_ACCOUNTANT},
        'audit_edit': ADMINS,
    },
    'reviews': {
        'view': ADMINS | {ROLE_MERCHANDISER},
        'moderate': ADMINS | {ROLE_MERCHANDISER},
        'answer': ADMINS | {ROLE_MERCHANDISER},
    },
    'reports': {
        'view': ADMINS | {ROLE_ACCOUNTANT},
        'export': ADMINS | {ROLE_ACCOUNTANT},
    },
    'audit': {
        'view': ADMINS,
        'export': ADMINS,
    },
    # Инфраструктурный контур данных — только Администратор БД (и главный администратор)
    'system': {
        'view': ADMINS,
    },
    'db': {
        'view': ADMINS,
        'backup': ADMINS,
        'restore': {ROLE_DB_ADMIN},
        'jobs': ADMINS,
        'archive': ADMINS,
        'grant_archive': {ROLE_DB_ADMIN},
        'service_accounts': ADMINS,
    },
    'archive': {
        # фактический доступ дополнительно ограничивается выданным временным грантом
        'view': ADMINS | {ROLE_ACCOUNTANT},
    },
    # Публичная часть: личные данные — только свои (проверка владельца в коде)
    'store': {
        'order': {ROLE_CUSTOMER} | ALL_STAFF,
        'review': {ROLE_CUSTOMER},
        'return': {ROLE_CUSTOMER},
    },
}

ACTION_LABELS = {
    'view': 'просмотр',
    'create': 'создание',
    'update': 'изменение',
    'delete': 'удаление',
    'change_role': 'смена роли',
    'import': 'импорт',
    'export': 'экспорт',
    'update_status': 'смена статуса',
    'cancel_critical': 'отмена (крит.)',
    'bulk': 'массовые операции',
    'mark_cod_paid': 'отметка оплаты при получении',
    'adjust_critical': 'корректировка (крит.)',
    'receipt': 'приход',
    'pick': 'сборка/списание',
    'print': 'печать накладных',
    'refund': 'возврат денег',
    'audit_edit': 'аудиторская правка',
    'moderate': 'модерация',
    'answer': 'ответ продавца',
    'backup': 'бэкап',
    'restore': 'restore',
    'jobs': 'регламентные задания',
    'archive': 'архивация',
    'grant_archive': 'выдача доступа к архиву',
    'service_accounts': 'сервисные учётки',
    'order': 'оформление заказа',
    'review': 'отзыв',
    'return': 'возврат',
}


def has_permission(role: str, resource: str, action: str) -> bool:
    """Проверяет, разрешено ли роли выполнить действие на ресурсе.

    DB_ADMIN — «царь и бог»: закрытых дверей перед ним нет. Оговорка одна:
    личные действия покупателя (store.*) ему не отдаём — он отвечает за
    целостность данных, а не за оформление чужих заказов, отзывов и возвратов.
    """
    if role == ROLE_DB_ADMIN and resource != 'store':
        return True
    resource_rules = PERMISSION_MATRIX.get(resource, {})
    allowed = resource_rules.get(action, set())
    return role in allowed
