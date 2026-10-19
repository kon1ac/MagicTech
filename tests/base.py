"""Общие фикстуры тестов: пользователи всех ролей, мини-каталог с ценами и остатками."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from django.core.cache import cache

from shop.models import Brand, Category, Characteristic, Product, Promotion, PromotionCategory, Stock
from shop.services import cart as cart_service
from shop.services import orders as order_service
from shop.services import payments as payment_service
from shop.services import pricing
from users.constants import (
    ROLE_ACCOUNTANT,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_DB_ADMIN,
    ROLE_MERCHANDISER,
    ROLE_PICKER,
)
from users.models import AuthCredentials, UserProfiles

PASSWORD = 'Passw0rd!'


def make_user(email, role):
    user = AuthCredentials(email=email, user_role=role)
    user.set_password(PASSWORD)
    user.save()
    UserProfiles.objects.create(id_user=user, profile_first_name='Тест', profile_address='Москва')
    return user


class MagicTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_user('admin@t.local', ROLE_ADMIN)
        cls.dbadmin = make_user('db@t.local', ROLE_DB_ADMIN)
        cls.merch = make_user('merch@t.local', ROLE_MERCHANDISER)
        cls.accountant = make_user('acc@t.local', ROLE_ACCOUNTANT)
        cls.picker = make_user('pick@t.local', ROLE_PICKER)
        cls.buyer = make_user('buyer@t.local', ROLE_CUSTOMER)
        cls.other_buyer = make_user('other@t.local', ROLE_CUSTOMER)
        cls.root = Category.objects.create(category_name='Устройства ввода', category_slug='input', category_level=1)
        cls.mice = Category.objects.create(category_name='Мыши', category_slug='mice', category_level=2, id_parent=cls.root)
        cls.keyboards = Category.objects.create(category_name='Клавиатуры', category_slug='kb', category_level=2, id_parent=cls.root)
        cls.brand = Brand.objects.create(brand_name='Logitech', brand_slug='logitech')
        Characteristic.objects.create(char_code='connection', char_name='Тип подключения')
        Characteristic.objects.create(char_code='color', char_name='Цвет')
        cls.mouse = cls.make_product('MS-001', 'Мышь Logitech G', cls.mice, Decimal('2000'), 10,
                                     {'connection': 'USB', 'color': 'Чёрный'})
        cls.keyboard = cls.make_product('KB-001', 'Клавиатура механическая', cls.keyboards, Decimal('5000'), 5,
                                        {'connection': 'Bluetooth', 'color': 'Белый'})

    def setUp(self):
        super().setUp()
        cache.clear()  # кеш каталога не должен переживать тест

    @classmethod
    def make_product(cls, sku, name, category, price, qty, chars=None):
        product = Product.objects.create(product_sku=sku, product_name=name, id_category=category, id_brand=cls.brand,
                                         product_characteristics=chars or {}, cost_price=price * Decimal('0.6'))
        pricing.set_price(product, price)
        Stock.objects.create(id_product=product, stock_quantity=qty, stock_reserved=0)
        return product

    def stock(self, product):
        return Stock.objects.get(id_product=product)

    def cart_with(self, user, *items):
        cart = cart_service.get_cart(user=user)
        for product, qty in items:
            cart_service.add_item(cart, product, qty)
        return cart

    def place_order(self, user=None, items=None, method='card_online', promo=None):
        user = user or self.buyer
        cart = self.cart_with(user, *(items or [(self.mouse, 1)]))
        if promo:
            cart.cart_promo_code = promo
            cart.save()
        return order_service.checkout(cart, user=user, payment_method=method, offer_accepted=True,
                                      delivery_address='Москва', contact_phone='+79990001122')

    def pay(self, payment):
        body = payment_service.build_webhook(payment, 'payment.succeeded')
        return payment_service.process_webhook(body, payment_service.sign(body))

    def promo(self, **kwargs):
        now = timezone.now()
        defaults = dict(promotion_name='Акция', promotion_type='percent', promotion_value=Decimal('10'),
                        start_at=now - timedelta(days=1), end_at=now + timedelta(days=1))
        defaults.update(kwargs)
        categories = defaults.pop('categories', [])
        promo = Promotion.objects.create(**defaults)
        for category in categories:
            PromotionCategory.objects.create(id_promotion=promo, id_category=category)
        return promo

    def login_panel(self, user):
        self.client.post('/panel/login/', {'email': user.email, 'password': PASSWORD}, secure=True)

    def login_store(self, user):
        self.client.post('/account/login/', {'email': user.email, 'password': PASSWORD})
