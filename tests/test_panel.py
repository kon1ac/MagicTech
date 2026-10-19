from shop.models import Order
from tests.base import MagicTestCase
from users.models import SavedFilter, UserSettings


class PanelTests(MagicTestCase):
    def test_main_pages_render_for_admin(self):
        self.place_order()
        self.login_panel(self.admin)
        for url in ('/panel/', '/panel/products/', '/panel/products/new/', f'/panel/products/{self.mouse.pk}/edit/',
                    '/panel/orders/', '/panel/stock/', '/panel/payments/', '/panel/returns/', '/panel/reviews/',
                    '/panel/reports/', '/panel/io/', '/panel/audit/', '/panel/db/', '/panel/db/schema/',
                    '/panel/db/backups/', '/panel/db/jobs/', '/panel/db/service-accounts/', '/panel/settings/',
                    '/panel/help/hotkeys/', '/panel/help/brandbook/', '/panel/users/rbac/', '/panel/references/'):
            self.assertEqual(self.client.get(url, secure=True).status_code, 200, url)

    def test_bulk_status_change_with_confirmation(self):
        o1, _ = self.place_order(method='cash_on_delivery')
        o2, _ = self.place_order(user=self.other_buyer, method='cash_on_delivery')
        self.login_panel(self.admin)
        self.client.post('/panel/orders/bulk/', {'ids': f'{o1.pk},{o2.pk}', 'new_status': 'CONFIRMED'})
        self.assertEqual(Order.objects.filter(order_status='CONFIRMED').count(), 0)  # без подтверждения
        self.client.post('/panel/orders/bulk/', {'ids': f'{o1.pk},{o2.pk}', 'new_status': 'CONFIRMED', 'confirm': '1'})
        self.assertEqual(Order.objects.filter(order_status='CONFIRMED').count(), 2)

    def test_settings_stored_on_server(self):
        self.login_panel(self.admin)
        self.client.post('/panel/settings/', {'theme': 'dark', 'language': 'en', 'date_format': 'Y-m-d H:i',
                                              'currency_format': 'rub_code', 'page_size': 50, 'hotkeys_enabled': 'on'})
        s = UserSettings.objects.get(id_user=self.admin)
        self.assertEqual((s.theme, s.language, s.page_size), ('dark', 'en', 50))
        r = self.client.get('/panel/')
        self.assertContains(r, 'data-theme="dark"')
        self.assertContains(r, 'Overview')

    def test_saved_and_default_filters(self):
        self.login_panel(self.admin)
        self.client.post('/panel/filters/save/', {'section': 'orders', 'name': 'Новые', 'query': 'status=NEW', 'as_default': '1'})
        self.assertTrue(SavedFilter.objects.filter(id_user=self.admin, filter_name='Новые').exists())
        r = self.client.get('/panel/orders/')
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r['Location'].endswith('?status=NEW'))

    def test_multi_column_sort(self):
        self.login_panel(self.admin)
        r = self.client.get('/panel/products/?sort=-price,sku')
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p.product_sku for p in r.context['page_obj']], ['KB-001', 'MS-001'])

    def test_pick_flow_and_documents(self):
        order, payment = self.place_order(method='cash_on_delivery')
        from shop.services import orders as order_service
        for status in ('CONFIRMED', 'ASSEMBLY'):
            order_service.change_order_status(order, status, actor=self.admin)
        self.login_panel(self.picker)
        item = order.items.get()
        r = self.client.post(f'/panel/orders/{order.pk}/pick/', {'confirm': '1'})
        self.assertEqual(Order.objects.get(pk=order.pk).order_status, 'ASSEMBLY')  # не отмечены товары
        self.client.post(f'/panel/orders/{order.pk}/pick/', {'picked': [item.pk], 'confirm': '1'})
        self.assertEqual(Order.objects.get(pk=order.pk).order_status, 'PACKED')
        r = self.client.get(f'/panel/orders/{order.pk}/invoice.pdf')
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertTrue(self.client.get(f'/panel/orders/{order.pk}/label.pdf').content.startswith(b'%PDF'))

    def test_exports(self):
        self.login_panel(self.admin)
        self.assertContains(self.client.get('/panel/io/export/catalog.xml'), '<offer id="MS-001"')
        self.assertIn('MS-001', self.client.get('/panel/io/export/catalog.csv').content.decode('utf-8'))
        self.assertEqual(self.client.get('/panel/reports/sales.csv').status_code, 200)


class StoreTests(MagicTestCase):
    def test_catalog_filters_server_side(self):
        r = self.client.get('/', {'f_connection': 'USB'})
        self.assertEqual([p.product_sku for p in r.context['page_obj']], ['MS-001'])
        r = self.client.get('/catalog/kb/')
        self.assertEqual([p.product_sku for p in r.context['page_obj']], ['KB-001'])
        r = self.client.get('/catalog/input/', {'price_max': '3000'})
        self.assertEqual([p.product_sku for p in r.context['page_obj']], ['MS-001'])
        facets = r.context['facets']
        self.assertIn('connection', [c['code'] for c in facets['chars']])

    def test_full_purchase_flow(self):
        self.client.post('/cart/add/', {'sku': 'MS-001', 'quantity': 2})
        self.assertEqual(self.stock(self.mouse).stock_reserved, 2)
        self.login_store(self.buyer)  # гостевая корзина переносится в аккаунт
        r = self.client.post('/checkout/', {'payment_method': 'card_online', 'delivery_address': 'Москва',
                                            'contact_phone': '+7 999 000-11-22', 'offer_accepted': 'on'})
        self.assertEqual(r.status_code, 302)
        order = Order.objects.get(id_user=self.buyer)
        self.client.post(r['Location'], {'result': 'success'})
        order.refresh_from_db()
        self.assertEqual(order.order_status, 'PAID')
        self.assertContains(self.client.get(f'/account/orders/{order.order_number}/'), order.order_number)

    def test_register_and_wishlist(self):
        r = self.client.post('/account/register/', {'email': 'new@t.local', 'first_name': 'Новый', 'password': 'Secret123',
                                                    'password2': 'Secret123'})
        self.assertEqual(r.status_code, 302)
        self.client.post(f'/product/{self.mouse.product_sku}/wishlist/')
        self.assertContains(self.client.get('/account/wishlist/'), self.mouse.product_name)
