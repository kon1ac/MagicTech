from django.test import Client, override_settings
from django.utils import timezone

from shop.models import AuditLog, Order, Review
from tests.base import PASSWORD, MagicTestCase
from users.models import AuthCredentials


class SecurityTests(MagicTestCase):
    def test_passwords_hashed_with_argon2(self):
        self.assertTrue(AuthCredentials.objects.get(pk=self.buyer.pk).password_hash.startswith('argon2'))

    def test_sql_injection_in_search_is_harmless(self):
        for payload in ["' OR 1=1 --", "'; DROP TABLE products; --", "%' UNION SELECT password_hash FROM auth_credentials --"]:
            r = self.client.get('/', {'q': payload, 'price_min': "1 OR 1=1", 'brand': "1;DROP"})
            self.assertEqual(r.status_code, 200)
            self.assertNotContains(r, 'argon2')
        self.assertEqual(self.client.get('/', {'q': 'Мышь'}).status_code, 200)
        from shop.models import Product
        self.assertTrue(Product.objects.exists())

    def test_customer_cannot_see_foreign_order(self):
        order, _ = self.place_order(user=self.other_buyer)
        self.login_store(self.buyer)
        self.assertEqual(self.client.get(f'/account/orders/{order.order_number}/').status_code, 404)
        self.assertEqual(self.client.post(f'/account/orders/{order.order_number}/cancel/').status_code, 404)
        self.assertEqual(Order.objects.get(pk=order.pk).order_status, 'NEW')

    def test_customer_cannot_enter_panel(self):
        r = self.client.post('/panel/login/', {'email': self.buyer.email, 'password': PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/panel/').status_code, 302)

    def test_privilege_escalation_blocked_on_server(self):
        self.login_panel(self.merch)
        r = self.client.post('/panel/users/new/', {'email': 'evil@t.local', 'user_role': 'ADMIN', 'is_active': 'on',
                                                    'password': 'Hacker123'})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(AuthCredentials.objects.filter(email='evil@t.local').exists())
        self.assertTrue(AuditLog.objects.filter(audit_object_type='access', audit_action='denied', id_user=self.merch).exists())

    def test_picker_cannot_cancel_or_change_status(self):
        order, _ = self.place_order(method='cash_on_delivery')
        self.login_panel(self.picker)
        self.client.post(f'/panel/orders/{order.pk}/', {'new_status': 'CANCELLED', 'reason': 'x', 'confirm_cancel': 'on'})
        self.assertEqual(Order.objects.get(pk=order.pk).order_status, 'NEW')
        self.assertEqual(self.client.post('/panel/orders/bulk/', {'ids': str(order.pk), 'new_status': 'CANCELLED',
                                                                   'confirm': '1'}).status_code, 403)

    def test_admin_cannot_change_own_role(self):
        self.login_panel(self.admin)
        self.client.post(f'/panel/users/{self.admin.pk}/edit/', {'email': self.admin.email, 'user_role': 'CUSTOMER',
                                                                 'is_active': 'on'})
        self.assertEqual(AuthCredentials.objects.get(pk=self.admin.pk).user_role, 'ADMIN')

    def test_accountant_has_no_db_access(self):
        self.login_panel(self.accountant)
        for url in ('/panel/db/', '/panel/db/backups/', '/panel/users/', '/panel/audit/'):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_db_access_is_audited(self):
        self.login_panel(self.dbadmin)
        self.assertEqual(self.client.get('/panel/db/', secure=True).status_code, 200)
        self.assertEqual(self.client.get('/panel/db/').status_code, 403)  # без HTTPS — отказ
        self.assertTrue(AuditLog.objects.filter(audit_object_type='db_access', id_user=self.dbadmin).exists())

    def test_dbadmin_has_every_panel_permission(self):
        """DB_ADMIN — «царь и бог»: ни одной закрытой двери. Кроме личных действий покупателя."""
        from users.constants import ROLE_DB_ADMIN
        from users.permissions import PERMISSION_MATRIX, has_permission

        for resource, actions in PERMISSION_MATRIX.items():
            for action, roles in actions.items():
                if resource == 'store':
                    # Личные данные (отзыв/возврат/заказ от имени покупателя) — не «власть над БД»,
                    # они и дальше проверяются матрицей и владельцем записи.
                    expected = ROLE_DB_ADMIN in roles
                else:
                    expected = True
                self.assertEqual(has_permission(ROLE_DB_ADMIN, resource, action), expected, f'{resource}.{action}')

    def test_ghost_user_cannot_log_in(self):
        ghost, _ = AuthCredentials.get_or_create_ghost()
        self.assertEqual(ghost.password_hash, '')  # пустая строка, не None
        self.assertEqual(ghost.user_role, 'GHOST')
        self.assertFalse(ghost.is_active)

    def test_dbadmin_deletes_buyer_with_orders_via_ghost(self):
        """Заказ с RESTRICT-ссылкой не должен давать 500: ссылки уходят на ghost, покупатель удаляется."""
        from users.models import AuthCredentials as AC

        order, _ = self.place_order(user=self.buyer)
        self.login_panel(self.dbadmin)
        r = self.client.post(f'/panel/users/{self.buyer.pk}/delete/', {'confirm': '1'})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(AuthCredentials.objects.filter(pk=self.buyer.pk).exists())
        ghost, _ = AC.get_or_create_ghost()
        self.assertEqual(Order.objects.get(pk=order.pk).id_user_id, ghost.pk)
        self.assertTrue(AuditLog.objects.filter(
            audit_object_type='user', audit_action='delete',
            id_user=self.dbadmin, audit_after__contains='"moved_to_ghost"'
        ).exists())
        # страница заказа не падает: email ghost на месте
        self.assertEqual(self.client.get(f'/panel/orders/{order.pk}/', secure=True).status_code, 200)

    def test_delete_user_without_orders_is_physical(self):
        self.login_panel(self.dbadmin)
        r = self.client.post(f'/panel/users/{self.other_buyer.pk}/delete/', {'confirm': '1'})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(AuthCredentials.objects.filter(pk=self.other_buyer.pk).exists())

    def test_cannot_delete_own_account(self):
        """Самоблокировка администратора: ни GET, ни POST не удаляют свою учётную запись."""
        self.login_panel(self.admin)
        for method in (self.client.get, self.client.post):
            r = method(f'/panel/users/{self.admin.pk}/delete/', {'confirm': '1'})
            self.assertEqual(r.status_code, 302)
            self.assertTrue(r['Location'].endswith('/panel/users/'))
            self.assertTrue(AuthCredentials.objects.filter(pk=self.admin.pk).exists())
        self.assertContains(self.client.get('/panel/users/', secure=True),
                            'Нельзя удалить собственную учётную запись')
        self.assertFalse(AuditLog.objects.filter(audit_object_type='user', object_id=self.admin.pk).exists())

    def test_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        r = client.post('/panel/login/', {'email': self.admin.email, 'password': PASSWORD})
        self.assertEqual(r.status_code, 403)

    def test_xss_escaped_in_reviews(self):
        Review.objects.create(id_product=self.mouse, id_user=self.buyer, review_type='review', review_rating=5,
                              review_text='<script>alert(1)</script>', review_status='approved')
        r = self.client.get(f'/product/{self.mouse.product_sku}/')
        self.assertNotContains(r, '<script>alert(1)</script>')
        self.assertContains(r, '&lt;script&gt;')

    def test_session_cookie_flags(self):
        from django.conf import settings
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertLessEqual(settings.SESSION_COOKIE_AGE, 8 * 3600)

    def test_open_redirect_blocked(self):
        r = self.client.post('/account/login/?next=https://evil.example/', {'email': self.buyer.email, 'password': PASSWORD})
        self.assertEqual(r['Location'], '/account/')

    @override_settings(MAGTECH_PANEL_LOGIN_MAX_ATTEMPTS=3)
    def test_panel_login_bruteforce_lockout(self):
        for _ in range(3):
            r = self.client.post('/panel/login/', {'email': self.admin.email, 'password': 'Wrong123'})
            self.assertEqual(r.status_code, 200)
        # после лимита даже верный пароль отклоняется с 429 — вход в панель закрыт
        r = self.client.post('/panel/login/', {'email': self.admin.email, 'password': PASSWORD}, secure=True)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(self.client.get('/panel/', secure=True).status_code, 302)

    @override_settings(MAGTECH_STORE_LOGIN_MAX_ATTEMPTS=3)
    def test_store_login_bruteforce_lockout(self):
        for _ in range(3):
            r = self.client.post('/account/login/', {'email': self.buyer.email, 'password': 'Wrong123'})
            self.assertEqual(r.status_code, 200)
        r = self.client.post('/account/login/', {'email': self.buyer.email, 'password': PASSWORD})
        self.assertEqual(r.status_code, 429)

    @override_settings(MAGTECH_PANEL_LOGIN_MAX_ATTEMPTS=3)
    def test_successful_login_resets_lockout_counter(self):
        for _ in range(2):
            self.client.post('/panel/login/', {'email': self.admin.email, 'password': 'Wrong123'})
        self.login_panel(self.admin)  # успешный вход обнуляет счётчик
        self.client.post('/panel/logout/')
        # 2 «сгоревшие» попытки не должны сложиться с новой третьей
        r = self.client.post('/panel/login/', {'email': self.admin.email, 'password': 'Wrong123'})
        self.assertEqual(r.status_code, 200)

    def test_is_authenticated_is_property_not_constant(self):
        """Несохранённый в БД экземпляр не должен считаться аутентифицированным."""
        self.assertFalse(AuthCredentials().is_authenticated)
        self.assertTrue(self.admin.is_authenticated)
        self.assertFalse(AuthCredentials().is_anonymous)

    def test_audit_survives_unserializable_payload(self):
        """Аудит пишется внутри бизнес-транзакций: не-JSON в snapshot не должен
        ронять операцию — значение приводится к строке."""
        from shop.services.audit import write_audit

        entry = write_audit(user=self.admin, object_type='test', object_id=self.admin.pk,
                            action='probe', after={'order': Order.objects.first(), 'when': timezone.now()})
        self.assertIsNotNone(entry.audit_after)
