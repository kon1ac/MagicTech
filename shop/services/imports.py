"""Импорт CSV/Excel: товары, остатки, цены, банковские выписки.

Схема одинаковая: чтение → сопоставление колонок → валидация ВСЕХ строк → запись одной
транзакцией (bulk-операции). Если хотя бы одна строка невалидна — ничего не пишется,
пользователь получает отчёт об ошибках с номерами строк.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from shop.models import (
    BankStatementImport,
    BankStatementLine,
    Brand,
    Category,
    ImportJob,
    Order,
    Price,
    Product,
    Stock,
    StockMovement,
)
from shop.services.audit import write_audit
from shop.services.catalog import invalidate_catalog_cache

PRODUCT_FIELDS = {
    'sku': ('Артикул', ['sku', 'артикул', 'article', 'product_sku']),
    'name': ('Название', ['name', 'название', 'наименование', 'product_name']),
    'price': ('Цена', ['price', 'цена', 'стоимость']),
    'category': ('Категория', ['category', 'категория']),
    'brand': ('Бренд', ['brand', 'бренд', 'производитель']),
    'stock': ('Остаток', ['stock', 'остаток', 'qty', 'quantity', 'количество']),
    'characteristics': ('Характеристики', ['characteristics', 'характеристики', 'attrs']),
    'description': ('Описание', ['description', 'описание']),
    'ean': ('EAN', ['ean', 'штрихкод', 'barcode']),
}
PRODUCT_REQUIRED = {'sku', 'name', 'price'}

STOCK_FIELDS = {
    'sku': ('Артикул', ['sku', 'артикул']),
    'quantity': ('Количество', ['quantity', 'qty', 'остаток', 'количество', 'stock']),
    'mode': ('Режим (set/add)', ['mode', 'режим']),
}
STOCK_REQUIRED = {'sku', 'quantity'}

PRICE_FIELDS = {
    'sku': ('Артикул', ['sku', 'артикул']),
    'price': ('Цена', ['price', 'цена']),
}
PRICE_REQUIRED = {'sku', 'price'}

STATEMENT_FIELDS = {
    'order_number': ('Номер заказа / назначение', ['order_number', 'номер заказа', 'назначение', 'назначение платежа', 'purpose']),
    'amount': ('Сумма', ['amount', 'сумма']),
    'date': ('Дата', ['date', 'дата', 'дата операции']),
}
STATEMENT_REQUIRED = {'order_number', 'amount'}

MAX_ROWS = 100_000
ORDER_RE = re.compile(r'MT-\d{6}-\d{6}', re.IGNORECASE)


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]] = field(default_factory=list)


def read_table(data: bytes, filename: str) -> Table:
    if filename.lower().endswith(('.xlsx', '.xlsm')):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheet = wb.active
        values = [['' if c is None else str(c) for c in row] for row in sheet.iter_rows(values_only=True)]
        if not values:
            raise ValidationError('Файл пуст.')
        return Table(headers=[h.strip() for h in values[0]], rows=values[1:MAX_ROWS + 1])
    for encoding in ('utf-8-sig', 'cp1251'):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValidationError('Не удалось определить кодировку (ожидается UTF-8 или Windows-1251).')
    sample = text[:4096]
    delimiter = ';' if sample.count(';') >= sample.count(',') else ','
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ValidationError('Файл пуст.')
    if len(rows) - 1 > MAX_ROWS:
        raise ValidationError(f'Слишком много строк (максимум {MAX_ROWS}).')
    return Table(headers=[h.strip() for h in rows[0]], rows=rows[1:])


def guess_mapping(headers: list[str], fields: dict) -> dict[str, int | None]:
    lowered = [h.strip().lower() for h in headers]
    mapping = {}
    for key, (_, aliases) in fields.items():
        mapping[key] = next((i for i, h in enumerate(lowered) if h in aliases), None)
    return mapping


def _cell(row, idx):
    if idx is None or idx >= len(row):
        return ''
    return (row[idx] or '').strip()


def _decimal(value: str) -> Decimal:
    value = value.replace(' ', '').replace(' ', '').replace(',', '.')
    return Decimal(value)


def _parse_chars(value: str) -> dict:
    if not value:
        return {}
    if value.startswith('{'):
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError
        return {str(k): v for k, v in data.items()}
    result = {}
    for part in value.split('|' if '|' in value else ';'):
        if not part.strip():
            continue
        key, _, val = part.partition('=')
        if not _ or not key.strip():
            raise ValueError
        result[slugify(key.strip(), allow_unicode=False) or key.strip()] = val.strip()
    return result


def _check_mapping(mapping, required, fields):
    missing = [fields[k][0] for k in required if mapping.get(k) is None]
    if missing:
        raise ValidationError('Не сопоставлены обязательные колонки: ' + ', '.join(missing))


def _finish(kind, file_name, actor, started, total, errors, ok_count=0):
    job = ImportJob.objects.create(
        import_kind=kind, file_name=file_name[:255],
        import_status='failed' if errors else 'success',
        rows_total=total, rows_ok=0 if errors else ok_count, rows_failed=len({e['row'] for e in errors}),
        import_errors=errors[:1000] or None, duration_ms=int((time.monotonic() - started) * 1000),
        id_user=actor,
    )
    return job


# ---------------------------------------------------------------- товары

def import_products(table: Table, mapping: dict, *, actor, file_name: str, request=None) -> ImportJob:
    started = time.monotonic()
    _check_mapping(mapping, PRODUCT_REQUIRED, PRODUCT_FIELDS)
    errors, parsed, seen_sku, seen_ean = [], [], {}, {}
    for n, row in enumerate(table.rows, start=2):  # строка 1 — заголовок
        def err(msg, n=n):
            errors.append({'row': n, 'error': msg})

        sku = _cell(row, mapping['sku'])
        name = _cell(row, mapping['name'])
        if not sku:
            err('Пустой артикул')
            continue
        if len(sku) > 100:
            err('Артикул длиннее 100 символов')
        if sku in seen_sku:
            err(f'Артикул {sku} повторяется (строка {seen_sku[sku]})')
        seen_sku[sku] = n
        if not name:
            err('Пустое название')
        try:
            price = _decimal(_cell(row, mapping['price']))
            if price < 0:
                err('Цена не может быть отрицательной')
            if price.as_tuple().exponent < -2:
                price = price.quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            err('Некорректная цена')
            price = None
        stock = None
        if mapping.get('stock') is not None and _cell(row, mapping['stock']):
            try:
                stock = int(_cell(row, mapping['stock']))
                if stock < 0:
                    err('Остаток не может быть отрицательным')
            except ValueError:
                err('Остаток должен быть целым числом')
        chars = None
        if mapping.get('characteristics') is not None:
            try:
                chars = _parse_chars(_cell(row, mapping['characteristics']))
            except (ValueError, json.JSONDecodeError):
                err('Характеристики: ожидается JSON или «ключ=значение;ключ=значение»')
        ean = _cell(row, mapping.get('ean')) or None
        if ean:
            if not ean.isdigit() or len(ean) not in (8, 12, 13, 14):
                err('EAN должен состоять из 8/12/13/14 цифр')
            if ean in seen_ean:
                err(f'EAN {ean} повторяется (строка {seen_ean[ean]})')
            seen_ean[ean] = n
        parsed.append({
            'row': n, 'sku': sku, 'name': name[:255], 'price': price, 'stock': stock, 'chars': chars,
            'category': _cell(row, mapping.get('category')), 'brand': _cell(row, mapping.get('brand')),
            'description': _cell(row, mapping.get('description')) or None, 'ean': ean,
        })

    existing = {p.product_sku: p for p in Product.objects.filter(product_sku__in=list(seen_sku))}
    if seen_ean:
        ean_owner = dict(Product.objects.filter(product_ean__in=list(seen_ean)).values_list('product_ean', 'product_sku'))
        for item in parsed:
            owner = ean_owner.get(item['ean'])
            if owner and owner != item['sku']:
                errors.append({'row': item['row'], 'error': f'EAN {item["ean"]} уже принадлежит товару {owner}'})
    stocks = {s.id_product_id: s for s in Stock.objects.filter(id_product__in=[p.pk for p in existing.values()])}
    for item in parsed:
        product = existing.get(item['sku'])
        if product and item['stock'] is not None and product.pk in stocks:
            if item['stock'] < stocks[product.pk].stock_reserved:
                errors.append({'row': item['row'], 'error': 'Остаток меньше зарезервированного количества'})

    if errors:
        errors.sort(key=lambda e: e['row'])
        return _finish('products', file_name, actor, started, len(table.rows), errors)

    with transaction.atomic():
        now = timezone.now()
        categories = {name.lower(): pk for pk, name in Category.objects.values_list('pk', 'category_name')}
        brands = {name.lower(): pk for pk, name in Brand.objects.values_list('pk', 'brand_name')}
        for item in parsed:
            cat = item['category']
            if cat and cat.lower() not in categories:
                obj = Category.objects.create(category_name=cat[:255], category_level=1,
                                              category_slug=_unique_slug(Category, 'category_slug', cat))
                categories[cat.lower()] = obj.pk
            br = item['brand']
            if br and br.lower() not in brands:
                obj = Brand.objects.create(brand_name=br[:255], brand_slug=_unique_slug(Brand, 'brand_slug', br))
                brands[br.lower()] = obj.pk

        new_products, updated = [], []
        for item in parsed:
            fields = {
                'product_name': item['name'],
                'id_category_id': categories.get(item['category'].lower()) if item['category'] else None,
                'id_brand_id': brands.get(item['brand'].lower()) if item['brand'] else None,
                'product_description': item['description'],
                'product_ean': item['ean'],
            }
            product = existing.get(item['sku'])
            if product:
                for key, value in fields.items():
                    if value is not None:
                        setattr(product, key, value)
                if item['chars'] is not None:
                    product.product_characteristics = item['chars']
                product.updated_at = now
                updated.append(product)
            else:
                new_products.append(Product(product_sku=item['sku'], product_characteristics=item['chars'] or {},
                                            is_active=True, **fields))
        Product.objects.bulk_create(new_products, batch_size=1000)
        Product.objects.bulk_update(
            updated, ['product_name', 'id_category_id', 'id_brand_id', 'product_description', 'product_ean',
                      'product_characteristics', 'updated_at'], batch_size=1000)
        by_sku = {p.product_sku: p for p in Product.objects.filter(product_sku__in=list(seen_sku))}

        current = dict(Price.objects.filter(id_product__in=by_sku.values(), valid_to__isnull=True)
                       .values_list('id_product_id', 'product_price'))
        changed = [it for it in parsed if current.get(by_sku[it['sku']].pk) != it['price']]
        Price.objects.filter(id_product__in=[by_sku[it['sku']].pk for it in changed], valid_to__isnull=True) \
            .update(valid_to=now)
        Price.objects.bulk_create([
            Price(id_product=by_sku[it['sku']], product_price=it['price'], id_user=actor,
                  price_reason=f'Импорт товаров: {file_name}'[:255]) for it in changed
        ], batch_size=1000)

        stock_rows = [it for it in parsed if it['stock'] is not None]
        stocks = {s.id_product_id: s for s in Stock.objects.filter(id_product__in=[by_sku[it['sku']].pk for it in stock_rows])}
        to_create, to_update, movements = [], [], []
        for it in stock_rows:
            product = by_sku[it['sku']]
            stock = stocks.get(product.pk)
            if stock is None:
                stock = Stock(id_product=product, stock_quantity=it['stock'], stock_reserved=0,
                              stock_movement_type='import')
                to_create.append(stock)
                delta = it['stock']
            else:
                delta = it['stock'] - stock.stock_quantity
                stock.stock_quantity = it['stock']
                stock.stock_movement_type = 'import'
                to_update.append(stock)
            if delta:
                movements.append(StockMovement(
                    id_product=product, movement_type='import', movement_quantity=delta,
                    quantity_after=stock.stock_quantity, reserved_after=stock.stock_reserved,
                    movement_reason=f'Импорт товаров: {file_name}'[:500], id_user=actor))
        Stock.objects.bulk_create(to_create, batch_size=1000)
        Stock.objects.bulk_update(to_update, ['stock_quantity', 'stock_movement_type'], batch_size=1000)
        StockMovement.objects.bulk_create(movements, batch_size=1000)

        job = _finish('products', file_name, actor, started, len(table.rows), [], len(parsed))
        write_audit(user=actor, object_type='import', object_id=job.pk, action='products',
                    after={'created': len(new_products), 'updated': len(updated),
                           'prices_changed': len(changed), 'file': file_name}, request=request)
    invalidate_catalog_cache()
    return job


def _unique_slug(model, field_name, text):
    base = slugify(text)[:200] or 'item'
    slug, n = base, 1
    while model.objects.filter(**{field_name: slug}).exists():
        n += 1
        slug = f'{base}-{n}'
    return slug


# ---------------------------------------------------------------- остатки

def import_stock(table: Table, mapping: dict, *, actor, file_name: str, default_mode='set', request=None) -> ImportJob:
    """Обновление остатков. Уход в минус или ниже резерва — запрет всей загрузки."""
    started = time.monotonic()
    _check_mapping(mapping, STOCK_REQUIRED, STOCK_FIELDS)
    rows, errors = [], []
    for n, row in enumerate(table.rows, start=2):
        sku = _cell(row, mapping['sku'])
        try:
            qty = int(_cell(row, mapping['quantity']))
        except ValueError:
            errors.append({'row': n, 'error': 'Количество должно быть целым числом'})
            continue
        mode = (_cell(row, mapping.get('mode')) or default_mode).lower()
        if mode not in {'set', 'add'}:
            errors.append({'row': n, 'error': 'Режим должен быть set или add'})
            continue
        rows.append((n, sku, qty, mode))
    products = {p.product_sku: p for p in Product.objects.filter(product_sku__in=[r[1] for r in rows])}
    for n, sku, qty, mode in rows:
        if sku not in products:
            errors.append({'row': n, 'error': f'Товар {sku} не найден'})

    if errors:
        return _finish('stock', file_name, actor, started, len(table.rows), sorted(errors, key=lambda e: e['row']))

    with transaction.atomic():
        ids = sorted(p.pk for p in products.values())
        for pid in ids:
            Stock.objects.get_or_create(id_product_id=pid, defaults={'stock_quantity': 0, 'stock_reserved': 0})
        stocks = {s.id_product_id: s for s in Stock.objects.select_for_update().filter(id_product__in=ids).order_by('id_product')}
        movements = []
        for n, sku, qty, mode in rows:
            stock = stocks[products[sku].pk]
            new_qty = qty if mode == 'set' else stock.stock_quantity + qty
            if new_qty < 0:
                errors.append({'row': n, 'error': f'{sku}: остаток уйдёт в минус ({new_qty})'})
                continue
            if new_qty < stock.stock_reserved:
                errors.append({'row': n, 'error': f'{sku}: остаток {new_qty} меньше резерва {stock.stock_reserved}'})
                continue
            delta = new_qty - stock.stock_quantity
            stock.stock_quantity = new_qty
            stock.stock_movement_type = 'import'
            if delta:
                movements.append(StockMovement(
                    id_product_id=stock.id_product_id, movement_type='import', movement_quantity=delta,
                    quantity_after=new_qty, reserved_after=stock.stock_reserved,
                    movement_reason=f'Импорт остатков: {file_name}'[:500], id_user=actor))
        if errors:
            transaction.set_rollback(True)
        else:
            Stock.objects.bulk_update(stocks.values(), ['stock_quantity', 'stock_movement_type'], batch_size=1000)
            StockMovement.objects.bulk_create(movements, batch_size=1000)
    job = _finish('stock', file_name, actor, started, len(table.rows), errors, len(rows))
    if not errors:
        write_audit(user=actor, object_type='import', object_id=job.pk, action='stock',
                    after={'rows': len(rows), 'movements': len(movements), 'file': file_name}, request=request)
    return job


# ---------------------------------------------------------------- цены

def import_prices(table: Table, mapping: dict, *, actor, file_name: str, request=None) -> ImportJob:
    """Цены с версионированием: старая версия закрывается, новая — с причиной и автором."""
    started = time.monotonic()
    _check_mapping(mapping, PRICE_REQUIRED, PRICE_FIELDS)
    rows, errors = [], []
    for n, row in enumerate(table.rows, start=2):
        sku = _cell(row, mapping['sku'])
        try:
            price = _decimal(_cell(row, mapping['price'])).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError):
            errors.append({'row': n, 'error': 'Некорректная цена'})
            continue
        if price < 0:
            errors.append({'row': n, 'error': 'Цена не может быть отрицательной'})
            continue
        rows.append((n, sku, price))
    products = {p.product_sku: p for p in Product.objects.filter(product_sku__in=[r[1] for r in rows])}
    for n, sku, _ in rows:
        if sku not in products:
            errors.append({'row': n, 'error': f'Товар {sku} не найден'})
    if errors:
        return _finish('prices', file_name, actor, started, len(table.rows), sorted(errors, key=lambda e: e['row']))

    with transaction.atomic():
        now = timezone.now()
        current = dict(Price.objects.filter(id_product__in=products.values(), valid_to__isnull=True)
                       .values_list('id_product_id', 'product_price'))
        changed = [(sku, price) for _, sku, price in rows if current.get(products[sku].pk) != price]
        Price.objects.filter(id_product__in=[products[s].pk for s, _ in changed], valid_to__isnull=True) \
            .update(valid_to=now)
        job = _finish('prices', file_name, actor, started, len(table.rows), [], len(rows))
        Price.objects.bulk_create([
            Price(id_product=products[sku], product_price=price, id_user=actor,
                  price_reason=f'Импорт цен #{job.pk}') for sku, price in changed
        ], batch_size=1000)
        write_audit(user=actor, object_type='import', object_id=job.pk, action='prices',
                    after={'changed': len(changed),
                           'sample': [{'sku': s, 'old': current.get(products[s].pk), 'new': p} for s, p in changed[:50]]},
                    request=request)
    invalidate_catalog_cache()
    return job


# ---------------------------------------------------------------- выписки

def _parse_date(value: str):
    for fmt in ('%d.%m.%Y', '%Y-%m-%d', '%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def import_bank_statement(table: Table, mapping: dict, *, actor, file_name: str, source='bank',
                          request=None) -> BankStatementImport:
    """Автоматическая сверка по номеру заказа/сумме/дате; несоответствия — в журнал."""
    from shop.services import payments as payment_service

    _check_mapping(mapping, STATEMENT_REQUIRED, STATEMENT_FIELDS)
    with transaction.atomic():
        imp = BankStatementImport.objects.create(file_name=file_name[:255], statement_source=source, id_user=actor)
        matched_orders = set(
            BankStatementLine.objects.filter(match_status='matched').values_list('id_order_id', flat=True)
        )
        lines = []
        for n, row in enumerate(table.rows, start=2):
            raw = dict(zip(table.headers, row))
            text = _cell(row, mapping['order_number'])
            found = ORDER_RE.search(text)
            number = found.group(0).upper() if found else None
            op_date = _parse_date(_cell(row, mapping.get('date'))) if mapping.get('date') is not None else None
            line = BankStatementLine(id_import=imp, row_number=n, order_number=number, operation_date=op_date,
                                     raw_data=raw)
            try:
                line.line_amount = _decimal(_cell(row, mapping['amount'])).quantize(Decimal('0.01'))
            except (InvalidOperation, ValueError):
                line.match_status, line.match_note = 'invalid', 'Не распознана сумма'
                lines.append(line)
                continue
            order = Order.objects.filter(order_number=number).first() if number else None
            line.id_order = order
            if not order:
                line.match_status, line.match_note = 'not_found', 'Заказ не найден'
            elif order.pk in matched_orders:
                line.match_status, line.match_note = 'duplicate', 'Оплата по заказу уже сверена ранее'
            elif line.line_amount != order.total:
                line.match_status = 'amount_mismatch'
                line.match_note = f'Сумма в выписке {line.line_amount} ≠ сумма заказа {order.total}'
            elif op_date and op_date < order.created_at.date():
                line.match_status, line.match_note = 'date_mismatch', 'Дата операции раньше даты заказа'
            else:
                payment = order.payments.filter(payment_amount=line.line_amount).exclude(payment_status='FAILED').first()
                if payment and payment.payment_status == 'PENDING':
                    payment_service.confirm_manually(payment, actor=actor, reason=f'Сверка с выпиской #{imp.pk}',
                                                     request=request)
                    payment.refresh_from_db()
                if payment and payment.payment_status in {'SUCCESS', 'REFUNDED', 'PARTIALLY_REFUNDED'}:
                    line.match_status, line.id_payment = 'matched', payment
                    matched_orders.add(order.pk)
                else:
                    line.match_status = 'no_payment'
                    line.match_note = 'Нет платежа по заказу (оплата при получении — отметьте вручную)'
            lines.append(line)
        BankStatementLine.objects.bulk_create(lines)
        imp.rows_total = len(lines)
        imp.rows_matched = sum(1 for line in lines if line.match_status == 'matched')
        imp.rows_mismatched = imp.rows_total - imp.rows_matched
        imp.save()
        write_audit(user=actor, object_type='bank_statement', object_id=imp.pk, action='import',
                    after={'rows': imp.rows_total, 'matched': imp.rows_matched}, request=request)
    return imp


def import_job_errors_csv(job: ImportJob) -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=';')
    writer.writerow(['Строка', 'Ошибка'])
    for error in job.import_errors or []:
        writer.writerow([error['row'], error['error']])
    return out.getvalue()
