from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from shop.models import Brand, Category, Order, OrderItem, Payment, Price, Product, Review, Stock
from users.constants import (
    ROLE_ACCOUNTANT,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_DB_ADMIN,
    ROLE_MERCHANDISER,
    ROLE_PICKER,
)
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
