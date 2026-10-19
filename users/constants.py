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

ORDER_ACTIVE_STATUSES = {'NEW', 'PAID', 'CONFIRMED', 'ASSEMBLY', 'PACKED'}
# Статусы, при которых товар уже списан со склада (отмена → обратная операция)
ORDER_WRITTEN_OFF_STATUSES = {'PACKED', 'COMPLETED'}

PAYMENT_STATUS_LABELS = {
    'PENDING': 'Ожидает',
    'SUCCESS': 'Успешно',
    'FAILED': 'Ошибка',
    'REFUNDED': 'Возвращён',
    'PARTIALLY_REFUNDED': 'Частичный возврат',
}

PAYMENT_METHOD_LABELS = {
    'card_online': 'Картой онлайн (ЮKassa)',
    'cash_on_delivery': 'При получении',
    'marketplace': 'Оплачен на маркетплейсе',
}
STORE_PAYMENT_METHODS = ('card_online', 'cash_on_delivery')

RETURN_STATUS_FLOW = {
    'NEW': {'IN_REVIEW', 'REJECTED'},
    'IN_REVIEW': {'APPROVED', 'REJECTED'},
    'APPROVED': {'RETURNED_TO_WAREHOUSE'},
    'RETURNED_TO_WAREHOUSE': {'REFUNDED', 'REPLACED'},
    'REJECTED': set(),
    'REFUNDED': set(),
    'REPLACED': set(),
}

RETURN_STATUS_LABELS = {
    'NEW': 'Новая заявка',
    'IN_REVIEW': 'На рассмотрении',
    'APPROVED': 'Одобрен',
    'REJECTED': 'Отклонён',
    'RETURNED_TO_WAREHOUSE': 'Принят на склад',
    'REFUNDED': 'Деньги возвращены',
    'REPLACED': 'Товар заменён',
}

# После одобрения заявка заблокирована — правки только аудиторские, с причиной
RETURN_LOCKED_STATUSES = {'APPROVED', 'RETURNED_TO_WAREHOUSE', 'REFUNDED', 'REPLACED', 'REJECTED'}

REVIEW_STATUS_LABELS = {'pending': 'На модерации', 'approved': 'Опубликован', 'rejected': 'Отклонён'}

PROMOTION_TYPE_LABELS = {'percent': 'Процент', 'fixed': 'Фиксированная сумма'}

# Области действия API-токенов
API_SCOPES = {
    'marketplace': 'Маркетплейсы: товары, остатки, цены, заказы, отгрузка',
    'mobile': 'Мобильное приложение покупателя',
    'internal': 'Внутренняя автоматизация: заказы и склад',
}
