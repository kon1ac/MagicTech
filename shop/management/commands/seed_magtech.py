<<<<<<< HEAD
"""Демо-данные MagicTech: пользователи всех ролей, дерево категорий, бренды, характеристики,
~60 товаров с ценами/остатками, акции и промокоды, заказы во всех статусах за 90 дней,
платежи, возвраты, отзывы, API-токены. Идемпотентна: повторный запуск ничего не дублирует."""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from shop.models import (
    Brand,
    Category,
    Characteristic,
    Order,
    Product,
    Promotion,
    PromotionCategory,
    ReturnReason,
    Review,
    Stock,
    Unit,
)
from shop.services import cart as cart_service
from shop.services import orders as order_service
from shop.services import payments as payment_service
from shop.services import pricing
from shop.services import returns as return_service
from shop.services import reviews as review_service
from shop.services.stock import adjust_stock, receive_stock, write_off_for_order
=======
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from shop.models import Brand, Category, Order, OrderItem, Payment, Price, Product, Review, Stock
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
from users.constants import (
    ROLE_ACCOUNTANT,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_DB_ADMIN,
    ROLE_MERCHANDISER,
    ROLE_PICKER,
)
<<<<<<< HEAD
from users.models import ApiToken, AuthCredentials, UserProfiles

STAFF = [
    ('admin@magtech.local', ROLE_ADMIN, 'Admin123!', 'Алексей', 'Системов'),
    ('db@magtech.local', ROLE_DB_ADMIN, 'DbAdmin123!', 'Мария', 'Данилова'),
    ('merch@magtech.local', ROLE_MERCHANDISER, 'Merch123!', 'Иван', 'Каталогов'),
    ('acc@magtech.local', ROLE_ACCOUNTANT, 'Acc123!', 'Ольга', 'Финова'),
    ('picker@magtech.local', ROLE_PICKER, 'Pick123!', 'Пётр', 'Складов'),
    ('marketplace-bot@magtech.local', ROLE_ADMIN, 'Service123!', 'Сервис', 'Маркетплейсы'),
]
CUSTOMERS = [
    ('buyer@example.com', 'Buyer123!', 'Анна', 'Покупатель'),
    ('gamer@example.com', 'Gamer123!', 'Дмитрий', 'Игроков'),
    ('office@example.com', 'Office123!', 'Елена', 'Офисная'),
    ('student@example.com', 'Student123!', 'Никита', 'Студентов'),
]

# (slug, name, parent_slug)
CATEGORIES = [
    ('input', 'Устройства ввода', None),
    ('keyboards', 'Клавиатуры', 'input'),
    ('keyboards-mech', 'Механические клавиатуры', 'keyboards'),
    ('keyboards-membrane', 'Мембранные клавиатуры', 'keyboards'),
    ('mice', 'Мыши', 'input'),
    ('mice-gaming', 'Игровые мыши', 'mice'),
    ('mice-office', 'Офисные мыши', 'mice'),
    ('mousepads', 'Коврики', 'input'),
    ('audio-video', 'Звук и видео', None),
    ('headsets', 'Наушники и гарнитуры', 'audio-video'),
    ('webcams', 'Веб-камеры', 'audio-video'),
    ('connectivity', 'Подключение', None),
    ('usb-hubs', 'USB-хабы', 'connectivity'),
    ('cables', 'Кабели', 'connectivity'),
    ('workspace', 'Рабочее место', None),
    ('laptop-stands', 'Подставки для ноутбуков', 'workspace'),
    ('cable-organizers', 'Органайзеры кабелей', 'workspace'),
    ('chairs', 'Игровые кресла', 'workspace'),
    ('care', 'Охлаждение и уход', None),
    ('cooling', 'Охлаждение', 'care'),
    ('thermal-paste', 'Термопаста', 'care'),
    ('wipes', 'Чистящие салфетки', 'care'),
    ('antistatic', 'Антистатические браслеты', 'care'),
]
BRANDS = ['Logitech', 'Razer', 'HyperX', 'SteelSeries', 'Keychron', 'A4Tech', 'Defender', 'Ugreen', 'Baseus',
          'Arctic', 'Noctua', 'DXRacer', 'Xiaomi', 'Trust']
CHARACTERISTICS = [
    ('connection', 'Тип подключения'), ('color', 'Цвет'), ('backlight', 'Подсветка'), ('material', 'Материал'),
    ('size', 'Размер'), ('switches', 'Переключатели'), ('dpi', 'Разрешение сенсора, DPI'),
    ('length', 'Длина кабеля'), ('ports', 'Количество портов'), ('resolution', 'Разрешение видео'),
]
# категория -> (префикс SKU, шаблон названия, цены, себестоимость %, генератор характеристик)
TEMPLATES = {
    'keyboards-mech': ('KB', ['{b} {m} TKL', '{b} {m} Full Size', '{b} {m} 65%'], (4990, 15990),
                       lambda r: {'connection': r.choice(['USB', 'Bluetooth', 'USB + 2.4 ГГц']), 'color': r.choice(['Чёрный', 'Белый', 'Серый']),
                                  'backlight': r.choice(['RGB', 'Белая', 'Нет']), 'switches': r.choice(['Red', 'Brown', 'Blue'])}),
    'keyboards-membrane': ('KM', ['{b} {m} Office', '{b} {m} Silent'], (990, 3490),
                           lambda r: {'connection': r.choice(['USB', '2.4 ГГц']), 'color': r.choice(['Чёрный', 'Белый']), 'backlight': 'Нет'}),
    'mice-gaming': ('MS', ['{b} {m} Pro', '{b} {m} Ultralight', '{b} {m} Wireless'], (2490, 12990),
                    lambda r: {'connection': r.choice(['USB', '2.4 ГГц', 'Bluetooth']), 'color': r.choice(['Чёрный', 'Белый', 'Розовый']),
                               'backlight': r.choice(['RGB', 'Нет']), 'dpi': r.choice(['16000', '26000', '30000'])}),
    'mice-office': ('MO', ['{b} {m} Silent', '{b} {m} Compact'], (590, 2490),
                    lambda r: {'connection': r.choice(['USB', '2.4 ГГц', 'Bluetooth']), 'color': r.choice(['Чёрный', 'Серый']), 'dpi': '1600'}),
    'mousepads': ('MP', ['{b} {m} XL', '{b} {m} Control', '{b} {m} Speed'], (490, 3990),
                  lambda r: {'size': r.choice(['M', 'L', 'XL', 'XXL']), 'material': r.choice(['Ткань', 'Пластик', 'Стекло']),
                             'backlight': r.choice(['RGB', 'Нет']), 'color': 'Чёрный'}),
    'headsets': ('HS', ['{b} {m} 7.1', '{b} {m} Wireless', '{b} {m} Studio'], (1990, 19990),
                 lambda r: {'connection': r.choice(['USB', '3.5 мм', '2.4 ГГц', 'Bluetooth']), 'color': r.choice(['Чёрный', 'Белый', 'Красный']),
                            'backlight': r.choice(['RGB', 'Нет'])}),
    'webcams': ('WC', ['{b} {m} HD', '{b} {m} Stream'], (1990, 14990),
                lambda r: {'resolution': r.choice(['720p', '1080p', '4K']), 'connection': 'USB', 'color': 'Чёрный'}),
    'usb-hubs': ('HB', ['{b} {m} 4-in-1', '{b} {m} 7-port'], (690, 4990),
                 lambda r: {'ports': r.choice(['4', '7', '10']), 'connection': r.choice(['USB-A', 'USB-C']), 'material': r.choice(['Алюминий', 'Пластик'])}),
    'cables': ('CB', ['{b} USB-C {m}', '{b} HDMI {m}', '{b} DisplayPort {m}'], (290, 2490),
               lambda r: {'length': r.choice(['1 м', '1.5 м', '2 м', '3 м']), 'connection': r.choice(['USB-C', 'HDMI', 'DisplayPort']),
                          'color': r.choice(['Чёрный', 'Белый'])}),
    'laptop-stands': ('LS', ['{b} {m} Stand', '{b} {m} Fold'], (990, 5990),
                      lambda r: {'material': r.choice(['Алюминий', 'Пластик']), 'color': r.choice(['Серебристый', 'Серый', 'Чёрный'])}),
    'cable-organizers': ('CO', ['{b} {m} Clip', '{b} {m} Box'], (190, 1490),
                         lambda r: {'material': r.choice(['Силикон', 'Пластик', 'Ткань']), 'color': r.choice(['Чёрный', 'Белый'])}),
    'chairs': ('CH', ['{b} {m} Gaming', '{b} {m} Racing'], (14990, 49990),
               lambda r: {'material': r.choice(['Экокожа', 'Ткань']), 'color': r.choice(['Чёрный', 'Красный', 'Синий'])}),
    'cooling': ('CL', ['{b} {m} Cooling Pad', '{b} {m} Fan 120'], (790, 4990),
                lambda r: {'size': r.choice(['120 мм', '140 мм', '15.6"', '17"']), 'backlight': r.choice(['RGB', 'Нет'])}),
    'thermal-paste': ('TP', ['{b} {m} 4 г', '{b} {m} 1.5 г'], (390, 1490), lambda r: {'material': 'Керамика'}),
    'wipes': ('WP', ['{b} {m} 100 шт.', '{b} {m} Screen'], (190, 690), lambda r: {'size': r.choice(['50 шт.', '100 шт.'])}),
    'antistatic': ('AS', ['{b} {m} ESD', '{b} {m} Wrist'], (190, 790), lambda r: {'length': r.choice(['1.8 м', '2 м']), 'color': 'Синий'}),
}
MODELS = ['Alpha', 'Nova', 'Pulse', 'Vector', 'Orbit', 'Prime', 'Edge', 'Flux']


class Command(BaseCommand):
    help = 'Заполняет демо-данные MagicTech (идемпотентно)'

    def add_arguments(self, parser):
        parser.add_argument('--orders', type=int, default=80, help='Сколько демо-заказов создать (при первом запуске)')

    def handle(self, *args, **options):
        from django.test.utils import override_settings

        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            self._handle(options)

    def _handle(self, options):
        rnd = random.Random(2026)
        with transaction.atomic():
            staff = self._users(rnd)
            self._catalog(rnd, staff['merch@magtech.local'])
            self._promotions(staff['admin@magtech.local'])
        if not Order.objects.exists():
            self._orders(rnd, options['orders'], staff)
        self._tokens(staff)
        self.stdout.write(self.style.SUCCESS(
            f'Готово: товаров {Product.objects.count()}, заказов {Order.objects.count()}, '
            f'отзывов {Review.objects.count()}.'))

    # ------------------------------------------------------------------
    def _users(self, rnd):
        result = {}
        for email, role, pwd, fn, ln in STAFF:
            user, created = AuthCredentials.objects.get_or_create(email=email, defaults={'user_role': role})
            if created or not user.check_password(pwd):
                user.set_password(pwd)
            user.user_role, user.is_active = role, True
            user.save()
            UserProfiles.objects.get_or_create(id_user=user, defaults={'profile_first_name': fn, 'profile_last_name': ln})
            result[email] = user
        for email, pwd, fn, ln in CUSTOMERS:
            user, created = AuthCredentials.objects.get_or_create(email=email, defaults={'user_role': ROLE_CUSTOMER})
            if created or not user.check_password(pwd):
                user.set_password(pwd)
                user.save()
            UserProfiles.objects.get_or_create(id_user=user, defaults={
                'profile_first_name': fn, 'profile_last_name': ln, 'profile_phone': f'+7 900 {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}',
                'profile_address': f'г. Москва, ул. Профсоюзная, д. {rnd.randint(1, 120)}, кв. {rnd.randint(1, 300)}'})
            result[email] = user
        return result

    def _catalog(self, rnd, merch):
        pcs = Unit.objects.filter(unit_code='pcs').first()
        for code, name in CHARACTERISTICS:
            Characteristic.objects.get_or_create(char_code=code, defaults={'char_name': name, 'id_unit': None})
        cats = {}
        for slug, name, parent in CATEGORIES:
            parent_obj = cats.get(parent)
            cat, _ = Category.objects.get_or_create(category_slug=slug, defaults={
                'category_name': name, 'id_parent': parent_obj,
                'category_level': (parent_obj.category_level + 1) if parent_obj else 1})
            cats[slug] = cat
        brands = {}
        for name in BRANDS:
            brands[name], _ = Brand.objects.get_or_create(brand_slug=name.lower(), defaults={'brand_name': name})
        if Product.objects.filter(product_sku__startswith='KB-').exists():
            return
        n = 0
        for slug, (prefix, names, (lo, hi), chars) in TEMPLATES.items():
            for i in range(4 if slug not in ('thermal-paste', 'wipes', 'antistatic') else 2):
                brand = rnd.choice(BRANDS)
                model = rnd.choice(MODELS)
                n += 1
                price = Decimal(rnd.randrange(lo, hi, 100) - 10)
                product = Product.objects.create(
                    product_sku=f'{prefix}-{brand[:3].upper()}-{n:03d}',
                    product_ean=f'460{rnd.randint(10**9, 10**10 - 1)}',
                    product_name=rnd.choice(names).format(b=brand, m=model),
                    id_brand=brands[brand], id_category=cats[slug], id_unit=pcs,
                    product_description=f'{cats[slug].category_name} {brand} {model}: надёжность, удобство и гарантия 1 год. '
                                        'Подходит для работы, учёбы и игр.',
                    product_characteristics=chars(rnd),
                    cost_price=(price * Decimal('0.62')).quantize(Decimal('1')),
                    seo_title=f'Купить {cats[slug].category_name.lower()} {brand} {model}',
                    seo_description=f'{brand} {model} в MagicTech: доставка по России, оплата картой онлайн.',
                )
                Product.objects.filter(pk=product.pk).update(created_at=timezone.now() - timedelta(days=rnd.randint(0, 200)))
                pricing.set_price(product, price, actor=merch, reason='Начальная цена')
                Stock.objects.create(id_product=product, stock_quantity=rnd.choice([0, 3, 8, 15, 25, 40, 60]),
                                     stock_reserved=0, stock_movement_type='receipt')

    def _promotions(self, admin):
        now = timezone.now()
        promo, created = Promotion.objects.get_or_create(promotion_name='Неделя периферии: −10% на мыши', defaults={
            'promotion_type': 'percent', 'promotion_value': Decimal('10'), 'start_at': now - timedelta(days=3),
            'end_at': now + timedelta(days=30), 'id_user': admin, 'promotion_description': 'Автоматическая скидка на категорию «Мыши»'})
        if created:
            PromotionCategory.objects.create(id_promotion=promo, id_category=Category.objects.get(category_slug='mice'))
        Promotion.objects.get_or_create(promotion_promo_code='MAGIC500', defaults={
            'promotion_name': 'Промокод −500 ₽ от 5000 ₽', 'promotion_type': 'fixed', 'promotion_value': Decimal('500'),
            'promotion_min_sum': Decimal('5000'), 'start_at': now - timedelta(days=10), 'end_at': now + timedelta(days=60),
            'usage_limit': 100, 'id_user': admin})
        Promotion.objects.get_or_create(promotion_promo_code='GAMER15', defaults={
            'promotion_name': 'Промокод −15% от 2 товаров', 'promotion_type': 'percent', 'promotion_value': Decimal('15'),
            'promotion_min_qty': 2, 'start_at': now - timedelta(days=10), 'end_at': now + timedelta(days=60),
            'usage_limit': 50, 'is_stackable': False, 'id_user': admin})

    def _orders(self, rnd, count, staff):
        """Заказы создаются через сервисы — с резервами, платежами, списаниями и аудитом, как в жизни."""
        admin, picker = staff['admin@magtech.local'], staff['picker@magtech.local']
        customers = [staff[c[0]] for c in CUSTOMERS]
        products = list(Product.objects.filter(is_active=True))
        for product in products:  # приход на склад, чтобы хватило на историю заказов
            receive_stock(product, 200, actor=picker, document_number='ПН-DEMO-001', reason='Демо-поступление')
        reasons = list(ReturnReason.objects.all())
        finals = ['COMPLETED'] * 45 + ['PACKED'] * 6 + ['ASSEMBLY'] * 6 + ['CONFIRMED'] * 6 + ['PAID'] * 5 + ['NEW'] * 4 + ['CANCELLED'] * 8
        created = 0
        for i in range(count):
            user = rnd.choice(customers)
            cart = cart_service.get_cart(user=user)
            cart.items.all().delete()
            for product in rnd.sample(products, rnd.randint(1, 3)):
                try:
                    cart_service.add_item(cart, product, rnd.randint(1, 2))
                except Exception:
                    continue
            if not cart.items.exists():
                continue
            if rnd.random() < 0.1:
                cart.cart_promo_code = 'MAGIC500'
                cart.save()
            method = 'card_online' if rnd.random() < 0.7 else 'cash_on_delivery'
            try:
                order, payment = order_service.checkout(
                    cart, user=user, payment_method=method, offer_accepted=True,
                    delivery_address=user.profile.profile_address or 'Москва', contact_phone=user.profile.profile_phone or '+79000000000')
            except Exception:
                cart_service.clear(cart)
                continue
            final = rnd.choice(finals)
            self._advance(order, payment, final, admin, picker, rnd)
            back = timezone.now() - timedelta(days=rnd.randint(0, 89), hours=rnd.randint(0, 23))
            Order.objects.filter(pk=order.pk).update(created_at=back, updated_at=back + timedelta(hours=rnd.randint(1, 72)))
            Order.objects.filter(pk=order.pk, paid_at__isnull=False).update(paid_at=back + timedelta(minutes=5))
            order.payments.update(created_at=back)
            order.payments.filter(paid_at__isnull=False).update(paid_at=back + timedelta(minutes=5))
            order.stock_movements.update(created_at=back + timedelta(hours=6))
            created += 1
            order.refresh_from_db()
            if order.order_status == 'COMPLETED':
                for item in order.items.all():
                    if rnd.random() < 0.45:
                        try:
                            review = review_service.create_review(
                                user, item.id_product, rating=rnd.choice([5, 5, 5, 4, 4, 3, 2]),
                                text=rnd.choice(['Отличный товар, рекомендую!', 'Пользуюсь месяц — всё работает.',
                                                 'Качество хорошее, доставка быстрая.', 'Ожидал большего, но за свои деньги норм.',
                                                 'Удобный, приятный материал.']))
                            review_service.moderate(review, rnd.choice(['approved', 'approved', 'approved', 'pending']), actor=admin)
                        except Exception:
                            pass
                if rnd.random() < 0.12 and reasons:
                    item = order.items.first()
                    ret = return_service.create_return(order, user=user, reason=rnd.choice(reasons),
                                                       description='Демо-возврат', quantities={item.pk: 1})
                    for status in rnd.choice([['IN_REVIEW'], ['IN_REVIEW', 'APPROVED', 'RETURNED_TO_WAREHOUSE', 'REFUNDED'], ['IN_REVIEW', 'REJECTED']]):
                        return_service.change_return_status(ret, status, actor=admin, decision='Демо-решение')
        for stock in Stock.objects.select_related('id_product'):  # приводим остатки к реалистичным
            target = stock.stock_reserved + rnd.choice([0, 2, 4, 7, 12, 20, 35, 50])
            if target != stock.stock_quantity:
                adjust_stock(stock.id_product, target - stock.stock_quantity, actor=admin,
                             reason='Инвентаризация (демо-данные)')
        self.stdout.write(f'Создано заказов: {created}')

    def _advance(self, order, payment, final, admin, picker, rnd):
        if final == 'NEW':
            return
        if final == 'CANCELLED':
            order_service.change_order_status(order, 'CANCELLED', actor=admin, reason='Демо: отмена по просьбе покупателя')
            return
        if payment:
            body = payment_service.build_webhook(payment, 'payment.succeeded')
            payment_service.process_webhook(body, payment_service.sign(body))
        chain = ['CONFIRMED', 'ASSEMBLY', 'PACKED', 'COMPLETED']
        target = {'PAID': 0, 'CONFIRMED': 1, 'ASSEMBLY': 2, 'PACKED': 3, 'COMPLETED': 4}[final]
        for status in chain[:target]:
            order.refresh_from_db()
            if status == 'PACKED':
                write_off_for_order(order, actor=picker)
                order_service.change_order_status(order, 'PACKED', actor=picker, reason='Собран', system=True)
            elif status == 'COMPLETED':
                if order.order_payment_status != 'SUCCESS':
                    payment_service.mark_cash_on_delivery_paid(order, actor=admin)
                order_service.change_order_status(order, 'COMPLETED', actor=admin, reason='Доставлен')
            else:
                order_service.change_order_status(order, status, actor=admin)

    def _tokens(self, staff):
        bot = staff['marketplace-bot@magtech.local']
        if not ApiToken.objects.filter(id_user=bot).exists():
            _, key = ApiToken.issue(bot, 'marketplace-demo', ['marketplace', 'internal'])
            self.stdout.write(self.style.WARNING(f'API-токен маркетплейса (сохраните, показывается один раз): {key}'))
=======
from users.models import AuthCredentials, UserProfiles


class Command(BaseCommand):
    help = 'Заполняет демо-данные MagicTech (каталог, заказы, пользователи панели)'

    def handle(self, *args, **options):
        staff = [
            ('admin@magtech.local', ROLE_ADMIN, 'Admin123!', 'Алексей', 'Системов'),
            ('db@magtech.local', ROLE_DB_ADMIN, 'DbAdmin123!', 'Мария', 'Данилова'),
            ('merch@magtech.local', ROLE_MERCHANDISER, 'Merch123!', 'Иван', 'Каталогов'),
            ('acc@magtech.local', ROLE_ACCOUNTANT, 'Acc123!', 'Ольга', 'Финова'),
            ('picker@magtech.local', ROLE_PICKER, 'Pick123!', 'Пётр', 'Складов'),
        ]
        for email, role, pwd, fn, ln in staff:
            user, created = AuthCredentials.objects.get_or_create(
                email=email,
                defaults={'user_role': role, 'is_active': True},
            )
            if created or not user.check_password(pwd):
                user.set_password(pwd)
                user.user_role = role
                user.is_active = True
                user.save()
            UserProfiles.objects.get_or_create(
                id_user=user,
                defaults={'profile_first_name': fn, 'profile_last_name': ln},
            )

        customer, _ = AuthCredentials.objects.get_or_create(
            email='buyer@example.com',
            defaults={'user_role': ROLE_CUSTOMER, 'is_active': True},
        )
        if not customer.password_hash.startswith('pbkdf2'):
            customer.set_password('Buyer123!')
            customer.save()

        cat_root, _ = Category.objects.get_or_create(
            category_slug='keyboards',
            defaults={
                'category_name': 'Клавиатуры',
                'category_level': 1,
                'is_active': True,
            },
        )
        brand, _ = Brand.objects.get_or_create(
            brand_slug='magpulse',
            defaults={'brand_name': 'MagPulse', 'is_active': True},
        )

        products_data = [
            ('MT-KB-001', 'MagPulse MK1 TKL', '4990.00', 24),
            ('MT-MS-014', 'MagPulse Pro Mouse', '3290.00', 40),
            ('MT-HP-007', 'Crystal Sound USB', '2190.00', 15),
        ]
        product_objs = []
        for sku, name, price, qty in products_data:
            product, _ = Product.objects.get_or_create(
                product_sku=sku,
                defaults={
                    'product_name': name,
                    'id_brand': brand,
                    'id_category': cat_root,
                    'product_description': f'{name} — аксессуар MagicTech.',
                    'product_characteristics': {'подключение': 'USB', 'цвет': 'чёрный'},
                    'is_active': True,
                },
            )
            Price.objects.get_or_create(
                id_product=product,
                product_price=Decimal(price),
                defaults={'price_currency': 'RUB'},
            )
            Stock.objects.update_or_create(
                id_product=product,
                defaults={'stock_quantity': qty, 'stock_reserved': 2},
            )
            product_objs.append(product)

        if not Order.objects.filter(order_number='MT-2026-0001').exists():
            order = Order.objects.create(
                order_number='MT-2026-0001',
                id_user=customer,
                order_status='ASSEMBLY',
                total_items=Decimal('8280.00'),
                discount_total=Decimal('0.00'),
                total=Decimal('8280.00'),
                order_payment_method='yookassa',
                order_payment_status='SUCCESS',
            )
            OrderItem.objects.create(
                id_order=order,
                id_product=product_objs[0],
                order_item_quantity=1,
                order_item_price=Decimal('4990.00'),
                order_item_total=Decimal('4990.00'),
            )
            OrderItem.objects.create(
                id_order=order,
                id_product=product_objs[1],
                order_item_quantity=1,
                order_item_price=Decimal('3290.00'),
                order_item_total=Decimal('3290.00'),
            )
            Payment.objects.create(
                id_order=order,
                payment_provider='yookassa',
                payment_amount=Decimal('8280.00'),
                payment_status='SUCCESS',
                id_user=customer,
            )

        if not Review.objects.filter(id_product=product_objs[0], id_user=customer).exists():
            Review.objects.create(
                id_product=product_objs[0],
                id_user=customer,
                review_type='review',
                review_rating=5,
                review_text='Отличная клавиатура, быстрая доставка.',
                review_status='pending',
            )

        self.stdout.write(self.style.SUCCESS('Демо-данные MagicTech загружены.'))
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
