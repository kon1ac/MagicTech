"""Матрица «Роль × Объект × Действие» — серверная авторизация панели."""

from users.constants import (
    ROLE_ACCOUNTANT,
    ROLE_ADMIN,
    ROLE_DB_ADMIN,
    ROLE_MERCHANDISER,
    ROLE_PICKER,
)

# resource -> action -> roles
PERMISSION_MATRIX = {
    'dashboard': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER, ROLE_ACCOUNTANT, ROLE_PICKER},
    },
    'users': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN},
        'create': {ROLE_ADMIN, ROLE_DB_ADMIN},
        'update': {ROLE_ADMIN, ROLE_DB_ADMIN},
        'delete': {ROLE_ADMIN, ROLE_DB_ADMIN},
    },
    'categories': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'create': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'update': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'delete': {ROLE_ADMIN, ROLE_DB_ADMIN},
    },
    'brands': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'create': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'update': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'delete': {ROLE_ADMIN, ROLE_DB_ADMIN},
    },
    'products': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER, ROLE_PICKER},
        'create': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'update': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'delete': {ROLE_ADMIN, ROLE_DB_ADMIN},
    },
    'promotions': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'create': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'update': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'delete': {ROLE_ADMIN, ROLE_DB_ADMIN},
    },
    'orders': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_ACCOUNTANT, ROLE_PICKER},
        'update_status': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_PICKER},
        'cancel_critical': {ROLE_ADMIN, ROLE_DB_ADMIN},
    },
    'stock': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER, ROLE_PICKER},
        'adjust_critical': {ROLE_ADMIN, ROLE_DB_ADMIN},
        'pick': {ROLE_ADMIN, ROLE_PICKER},
    },
    'payments': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_ACCOUNTANT},
        'update': {ROLE_ADMIN, ROLE_ACCOUNTANT},
    },
    'returns': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_ACCOUNTANT},
        'update': {ROLE_ADMIN, ROLE_ACCOUNTANT},
    },
    'reviews': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
        'moderate': {ROLE_ADMIN, ROLE_DB_ADMIN, ROLE_MERCHANDISER},
    },
    'audit': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN},
        'export': {ROLE_ADMIN, ROLE_DB_ADMIN},
    },
    'system': {
        'view': {ROLE_ADMIN, ROLE_DB_ADMIN},
    },
}


def has_permission(role: str, resource: str, action: str) -> bool:
    resource_rules = PERMISSION_MATRIX.get(resource, {})
    allowed = resource_rules.get(action, set())
    return role in allowed
