
from decimal import Decimal

from rest_framework.test import APIClient

from shop.models import AuditLog, Order
from shop.services import payments as payment_service
from tests.base import PASSWORD, MagicTestCase
from users.models import ApiToken


class ApiTests(MagicTestCase):
    def setUp(self):
        self.api = APIClient()
        _, self.mp_key = ApiToken.issue(self.admin, 'marketplace', ['marketplace', 'internal'])
        _, self.picker_key = ApiToken.issue(self.picker, 'picker', ['internal'])

    def auth(self, key):
        self.api.credentials(HTTP_AUTHORIZATION=f'Token {key}')

    def test_requires_token_and_scope(self):
        self.assertEqual(self.api.get('/api/v1/marketplace/stock/').status_code, 401)
        self.auth(self.picker_key)
        r = self.api.get('/api/v1/marketplace/stock/')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()['error']['code'], 'forbidden')
        self.assertTrue(AuditLog.objects.filter(audit_object_type='api', audit_action='error_403').exists())

    def test_marketplace_exports(self):
        self.auth(self.mp_key)
        stock = self.api.get('/api/v1/marketplace/stock/').json()
        self.assertEqual({r['sku'] for r in stock['results']}, {'MS-001', 'KB-001'})
        prices = self.api.get('/api/v1/marketplace/prices/').json()['results']
        self.assertEqual(len(prices), 2)
        products = self.api.get('/api/v1/marketplace/products/').json()
        self.assertEqual(products['count'], 2)

    def test_marketplace_order_import_and_ship(self):
        self.auth(self.mp_key)
        payload = {'external_order_id': 'OZ-1', 'marketplace': 'ozon', 'customer_email': 'mp@buyer.ru',
                   'delivery_address': 'ПВЗ', 'contact_phone': '+79990000000', 'items': [{'sku': 'MS-001', 'quantity': 2}]}
        r = self.api.post('/api/v1/marketplace/orders/', payload, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        number = r.json()['order_number']
        self.assertEqual(r.json()['order_status'], 'PAID')
        self.assertEqual(self.api.post('/api/v1/marketplace/orders/', payload, format='json').status_code, 409)
        self.assertEqual(self.api.post(f'/api/v1/marketplace/orders/{number}/ship/', {}, format='json').status_code, 400)

    def test_marketplace_order_rolls_back_on_missing_stock(self):
        self.auth(self.mp_key)
        r = self.api.post('/api/v1/marketplace/orders/', {
            'external_order_id': 'OZ-2', 'marketplace': 'ozon', 'customer_email': 'x@y.ru', 'delivery_address': 'a',
            'contact_phone': '1', 'items': [{'sku': 'MS-001', 'quantity': 1}, {'sku': 'KB-001', 'quantity': 99}]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Недостаточно', r.json()['error']['message'])
        self.assertFalse(Order.objects.exists())
        self.assertEqual(self.stock(self.mouse).stock_reserved, 0)

    def test_mobile_flow(self):
        r = self.api.post('/api/v1/mobile/auth/token/', {'email': self.buyer.email, 'password': PASSWORD}, format='json')
        self.assertEqual(r.status_code, 200)
        self.auth(r.json()['token'])
        cart = self.api.post('/api/v1/mobile/cart/items/', {'sku': 'KB-001', 'quantity': 2}, format='json').json()
        self.assertEqual(cart['total'], '10000.00')
        r = self.api.post('/api/v1/mobile/orders/', {'payment_method': 'card_online', 'delivery_address': 'Москва',
                                                     'contact_phone': '+7999', 'offer_accepted': True}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        number = r.json()['order_number']
        self.assertIn('payment', r.json())
        self.assertEqual(self.api.get(f'/api/v1/mobile/orders/{number}/').status_code, 200)
        # чужой заказ не виден
        other, _ = self.place_order(user=self.other_buyer)
        self.assertEqual(self.api.get(f'/api/v1/mobile/orders/{other.order_number}/').status_code, 404)

    def test_staff_token_cannot_use_mobile_api(self):
        token, key = ApiToken.issue(self.admin, 'x', ['mobile'])
        self.auth(key)
        self.assertEqual(self.api.get('/api/v1/mobile/cart/').status_code, 403)

    def test_public_catalog(self):
        r = self.api.get('/api/v1/mobile/catalog/products/', {'q': 'Мышь', 'sort': 'price_asc'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p['product_sku'] for p in r.json()['results']], ['MS-001'])
        self.assertEqual(self.api.get('/api/v1/mobile/catalog/products/NOPE/').status_code, 404)

    def test_webhook_endpoint(self):
        order, payment = self.place_order()
        body = payment_service.build_webhook(payment, 'payment.succeeded')
        bad = self.api.post('/api/v1/payments/yookassa/webhook/', data=body, content_type='application/json',
                            HTTP_X_SIGNATURE='bad')
        self.assertEqual(bad.status_code, 403)
        ok = self.api.post('/api/v1/payments/yookassa/webhook/', data=body, content_type='application/json',
                           HTTP_X_SIGNATURE=payment_service.sign(body))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(Order.objects.get(pk=order.pk).order_status, 'PAID')

    def test_internal_rbac(self):
        order, _ = self.place_order(method='cash_on_delivery')
        self.auth(self.picker_key)
        r = self.api.post(f'/api/v1/internal/orders/{order.order_number}/status/', {'status': 'CONFIRMED'}, format='json')
        self.assertEqual(r.status_code, 403)
        r = self.api.post('/api/v1/internal/stock/MS-001/receipt/', {'quantity': 5, 'reason': 'Поставка'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['quantity'], 15)
        self.auth(self.mp_key)
        r = self.api.post(f'/api/v1/internal/orders/{order.order_number}/status/', {'status': 'ASSEMBLY'}, format='json')
        self.assertEqual(r.status_code, 400)  # перескок этапа
        r = self.api.post(f'/api/v1/internal/orders/{order.order_number}/status/', {'status': 'CONFIRMED'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_order_contract_uses_subtotal(self):
        """Сумма товаров до скидки отдаётся как subtotal; старое имя total_items ушло из контракта."""
        order, _ = self.place_order()
        self.auth(self.mp_key)
        row = next(r for r in self.api.get('/api/v1/internal/orders/').json()['results']
                   if r['order_number'] == order.order_number)
        self.assertEqual(Decimal(row['subtotal']), order.subtotal)
        self.assertNotIn('total_items', row)

    def test_openapi_schema(self):
        r = self.client.get('/api/schema/')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'/api/v1/payments/yookassa/webhook/', r.content)
