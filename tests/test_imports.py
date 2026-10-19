from decimal import Decimal

from shop.models import BankStatementLine, Price, Product
from shop.services import imports
from tests.base import MagicTestCase


def table(text):
    return imports.read_table(text.encode('utf-8'), 'f.csv')


class ImportTests(MagicTestCase):
    def test_product_import_creates_and_updates(self):
        t = table('sku;name;price;category;brand;stock;characteristics\n'
                  'MS-001;Мышь новая;2100;Мыши;Logitech;12;color=Белый\n'
                  'NEW-1;Коврик XL;990;Коврики;Ugreen;30;"size=XL;material=Ткань"\n')
        job = imports.import_products(t, imports.guess_mapping(t.headers, imports.PRODUCT_FIELDS), actor=self.merch, file_name='f.csv')
        self.assertEqual(job.import_status, 'success', job.import_errors)
        self.assertEqual(Product.objects.get(product_sku='MS-001').current_price, Decimal('2100'))
        new = Product.objects.get(product_sku='NEW-1')
        self.assertEqual(new.product_characteristics, {'size': 'XL', 'material': 'Ткань'})
        self.assertEqual(new.id_category.category_name, 'Коврики')
        self.assertEqual(self.stock(new).stock_quantity, 30)

    def test_product_import_all_or_nothing_with_row_numbers(self):
        t = table('sku,name,price\nOK-1,Хороший,100\nBAD-1,Плохой,-5\n,Без артикула,10\nOK-1,Дубль,10\n')
        job = imports.import_products(t, imports.guess_mapping(t.headers, imports.PRODUCT_FIELDS), actor=self.merch, file_name='f.csv')
        self.assertEqual(job.import_status, 'failed')
        rows = sorted({e['row'] for e in job.import_errors})
        self.assertEqual(rows, [3, 4, 5])
        self.assertFalse(Product.objects.filter(product_sku='OK-1').exists())

    def test_stock_import_forbids_negative(self):
        t = table('sku;quantity;mode\nMS-001;-20;add\nKB-001;3;set\n')
        job = imports.import_stock(t, imports.guess_mapping(t.headers, imports.STOCK_FIELDS), actor=self.admin, file_name='s.csv')
        self.assertEqual(job.import_status, 'failed')
        self.assertEqual(self.stock(self.keyboard).stock_quantity, 5)  # ничего не изменено

    def test_stock_import_ok(self):
        t = table('sku;quantity\nMS-001;25\n')
        job = imports.import_stock(t, imports.guess_mapping(t.headers, imports.STOCK_FIELDS), actor=self.admin, file_name='s.csv')
        self.assertEqual(job.import_status, 'success')
        self.assertEqual(self.stock(self.mouse).stock_quantity, 25)

    def test_price_import_versions(self):
        t = table('sku;price\nMS-001;1999,90\nKB-001;5000\n')
        job = imports.import_prices(t, imports.guess_mapping(t.headers, imports.PRICE_FIELDS), actor=self.merch, file_name='p.csv')
        self.assertEqual(job.import_status, 'success')
        self.assertEqual(self.mouse.current_price, Decimal('1999.90'))
        self.assertEqual(Price.objects.filter(id_product=self.keyboard).count(), 1)  # цена не изменилась — версия не создаётся
        self.assertTrue(Price.objects.filter(price_reason=f'Импорт цен #{job.pk}').exists())

    def test_bank_statement_matching(self):
        order, payment = self.place_order()
        t = table(f'date;purpose;amount\n01.01.2030;Оплата заказа {order.order_number};2000.00\n'
                  f'01.01.2030;Оплата заказа {order.order_number};2000.00\n'
                  '01.01.2030;Оплата MT-000000-999999;10\n01.01.2030;что-то;abc\n')
        imp = imports.import_bank_statement(t, imports.guess_mapping(t.headers, imports.STATEMENT_FIELDS), actor=self.accountant, file_name='b.csv')
        statuses = list(BankStatementLine.objects.filter(id_import=imp).order_by('row_number').values_list('match_status', flat=True))
        self.assertEqual(statuses, ['matched', 'duplicate', 'not_found', 'invalid'])
        payment.refresh_from_db()
        self.assertEqual(payment.payment_status, 'SUCCESS')  # PENDING-платёж подтверждён сверкой

    def test_import_10k_products_performance(self):
        import time
        rows = ['sku;name;price;category;brand;stock'] + [f'P-{i:05d};Товар {i};{100 + i % 900};Кат {i % 20};Бренд {i % 30};{i % 50}' for i in range(10_000)]
        t = table('\n'.join(rows))
        started = time.monotonic()
        job = imports.import_products(t, imports.guess_mapping(t.headers, imports.PRODUCT_FIELDS), actor=self.merch, file_name='big.csv')
        elapsed = time.monotonic() - started
        self.assertEqual(job.import_status, 'success', job.import_errors[:3] if job.import_errors else None)
        self.assertLess(elapsed, 30, f'Импорт 10k занял {elapsed:.1f} с')
        print(f'\n[perf] импорт 10 000 товаров: {elapsed:.2f} с')
