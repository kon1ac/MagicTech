"""Роли и коды ресурсов для RBAC MagicTech."""

ROLE_ADMIN = 'ADMIN'
ROLE_DB_ADMIN = 'DB_ADMIN'
ROLE_MERCHANDISER = 'MERCHANDISER'
ROLE_ACCOUNTANT = 'ACCOUNTANT'
ROLE_PICKER = 'PICKER'
ROLE_CUSTOMER = 'CUSTOMER'

ROLE_CHOICES = [
    (ROLE_ADMIN, 'Администратор'),
    (ROLE_DB_ADMIN, 'Администратор БД'),
    (ROLE_MERCHANDISER, 'Товаровед'),
    (ROLE_ACCOUNTANT, 'Бухгалтер / финансист'),
    (ROLE_PICKER, 'Сборщик заказов'),
    (ROLE_CUSTOMER, 'Покупатель'),
]

STAFF_ROLES = {
    ROLE_ADMIN,
    ROLE_DB_ADMIN,
    ROLE_MERCHANDISER,
    ROLE_ACCOUNTANT,
    ROLE_PICKER,
}

ROLE_LABELS = dict(ROLE_CHOICES)

ORDER_STATUS_FLOW = {
    'NEW': {'PAID', 'CONFIRMED', 'CANCELLED'},
    'PAID': {'CONFIRMED', 'CANCELLED'},
    'CONFIRMED': {'ASSEMBLY', 'CANCELLED'},
    'ASSEMBLY': {'PACKED', 'CANCELLED'},
    'PACKED': {'COMPLETED', 'CANCELLED'},
    'COMPLETED': {'RETURNED'},
    'CANCELLED': set(),
    'RETURNED': set(),
}

ORDER_STATUS_LABELS = {
    'NEW': 'Новый',
    'PAID': 'Оплачен',
    'CONFIRMED': 'Подтверждён',
    'ASSEMBLY': 'В сборке',
    'PACKED': 'Собран',
    'COMPLETED': 'Завершён',
    'CANCELLED': 'Отменён',
    'RETURNED': 'Возврат',
}
