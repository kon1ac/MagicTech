"""Экспорт: каталог (CSV/XML для маркетплейсов), заказы (CSV), накладные и ярлыки (PDF)."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from xml.sax.saxutils import escape

from django.utils import timezone

from shop.models import Category, Order
from shop.services.catalog import base_queryset
from users.constants import ORDER_STATUS_LABELS, PAYMENT_METHOD_LABELS

FONT_CANDIDATES = [
    Path(__file__).resolve().parent.parent.parent / 'static' / 'fonts' / 'DejaVuSans.ttf',
    Path('/usr/share/fonts/TTF/DejaVuSans.ttf'),
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
    Path('/usr/share/fonts/liberation/LiberationSans-Regular.ttf'),
    Path('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'),
    Path('C:/Windows/Fonts/arial.ttf'),
]


def csv_bytes(header: list[str], rows) -> bytes:
    out = io.StringIO()
    out.write('\ufeff')  # BOM — корректное открытие в Excel
    writer = csv.writer(out, delimiter=';')
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    return out.getvalue().encode('utf-8')


def catalog_csv() -> bytes:
    rows = (
        [p.product_sku, p.product_name, p.id_brand.brand_name if p.id_brand else '',
         p.id_category.category_name if p.id_category else '', p.price_now or '', max(p.available, 0),
         p.product_ean or '']
        for p in base_queryset().order_by('product_sku').iterator(chunk_size=2000)
    )
    return csv_bytes(['sku', 'name', 'brand', 'category', 'price', 'stock', 'ean'], rows)


def catalog_xml(base_url: str = '') -> bytes:
    """Формат YML (Яндекс.Маркет) — принимается большинством маркетплейсов."""
    now = timezone.localtime().strftime('%Y-%m-%d %H:%M')
    parts = [f'<?xml version="1.0" encoding="UTF-8"?>\n<yml_catalog date="{now}"><shop>',
             '<name>MagicTech</name><company>MagicTech</company>',
             f'<url>{escape(base_url or "https://magictech.local")}</url>',
             '<currencies><currency id="RUR" rate="1"/></currencies><categories>']
    for cat in Category.objects.filter(is_active=True).order_by('pk'):
        parent = f' parentId="{cat.id_parent_id}"' if cat.id_parent_id else ''
        parts.append(f'<category id="{cat.pk}"{parent}>{escape(cat.category_name)}</category>')
    parts.append('</categories><offers>')
    for p in base_queryset().filter(price_now__isnull=False).order_by('pk').iterator(chunk_size=2000):
        available = 'true' if p.available > 0 else 'false'
        parts.append(
            f'<offer id="{escape(p.product_sku)}" available="{available}">'
            f'<url>{escape(base_url)}/product/{escape(p.product_sku)}/</url>'
            f'<price>{p.price_now}</price><currencyId>RUR</currencyId>'
            f'<categoryId>{p.id_category_id or ""}</categoryId>'
            f'<vendor>{escape(p.id_brand.brand_name if p.id_brand else "")}</vendor>'
            f'<name>{escape(p.product_name)}</name><count>{max(p.available, 0)}</count>'
            + (f'<barcode>{escape(p.product_ean)}</barcode>' if p.product_ean else '')
            + '</offer>'
        )
    parts.append('</offers></shop></yml_catalog>')
    return ''.join(parts).encode('utf-8')


def orders_csv(queryset) -> bytes:
    rows = (
        [o.order_number, timezone.localtime(o.created_at).strftime('%d.%m.%Y %H:%M'), o.id_user.email,
         ORDER_STATUS_LABELS.get(o.order_status, o.order_status),
         PAYMENT_METHOD_LABELS.get(o.order_payment_method, o.order_payment_method or ''),
         o.order_payment_status or '', o.subtotal, o.discount_total, o.total, o.order_channel]
        for o in queryset.select_related('id_user').iterator(chunk_size=2000)
    )
    return csv_bytes(['Номер', 'Дата', 'Покупатель', 'Статус', 'Способ оплаты', 'Статус оплаты',
                      'Сумма товаров', 'Скидка', 'Итого', 'Канал'], rows)


def _pdf_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if 'MTSans' in pdfmetrics.getRegisteredFontNames():
        return 'MTSans'
    for path in FONT_CANDIDATES:
        if path.exists():
            pdfmetrics.registerFont(TTFont('MTSans', str(path)))
            return 'MTSans'
    return 'Helvetica'  # кириллица не отобразится — положите шрифт в static/fonts/DejaVuSans.ttf


def invoice_pdf(order: Order) -> bytes:
    """Товарная накладная по заказу."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle

    font = _pdf_font()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            title=f'Накладная {order.order_number}')
    h = ParagraphStyle('h', fontName=font, fontSize=16, leading=20, textColor=colors.HexColor('#312e81'))
    p = ParagraphStyle('p', fontName=font, fontSize=10, leading=14)
    customer = order.id_user
    profile = getattr(customer, 'profile', None)
    name = f'{profile.profile_first_name or ""} {profile.profile_last_name or ""}'.strip() if profile else ''
    story = [
        Paragraph(f'MagicTech — товарная накладная № {order.order_number}', h),
        Paragraph(f'Дата заказа: {timezone.localtime(order.created_at):%d.%m.%Y %H:%M}', p),
        Paragraph(f'Покупатель: {escape(name or customer.email)} · {escape(customer.email)}', p),
        Paragraph(f'Адрес доставки: {escape(order.delivery_address or "—")}', p),
        Paragraph(f'Оплата: {PAYMENT_METHOD_LABELS.get(order.order_payment_method, "—")} '
                  f'({order.order_payment_status or "—"})', p),
        Spacer(1, 6 * mm),
    ]
    data = [['№', 'Артикул', 'Наименование', 'Кол-во', 'Цена', 'Скидка', 'Сумма']]
    for i, item in enumerate(order.items.select_related('id_product'), start=1):
        data.append([i, item.id_product.product_sku, Paragraph(escape(item.id_product.product_name), p),
                     item.order_item_quantity, f'{item.order_item_price}', f'{item.order_item_discount}',
                     f'{item.order_item_total}'])
    data.append(['', '', 'Итого', '', '', f'{order.discount_total}', f'{order.total}'])
    table = Table(data, colWidths=[8 * mm, 28 * mm, 70 * mm, 15 * mm, 20 * mm, 18 * mm, 22 * mm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story += [table, Spacer(1, 12 * mm),
              Paragraph('Отпустил: ____________________ &nbsp;&nbsp;&nbsp; Получил: ____________________', p)]
    doc.build(story)
    return buf.getvalue()


def label_pdf(order: Order) -> bytes:
    """Ярлык на коробку 100×70 мм со штрихкодом номера заказа."""
    from reportlab.graphics.barcode import code128
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    font = _pdf_font()
    buf = io.BytesIO()
    width, height = 100 * mm, 70 * mm
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setTitle(f'Ярлык {order.order_number}')
    c.setFont(font, 14)
    c.drawString(6 * mm, height - 10 * mm, 'MagicTech')
    c.setFont(font, 11)
    c.drawString(6 * mm, height - 17 * mm, f'Заказ: {order.order_number}')
    c.setFont(font, 9)
    c.drawString(6 * mm, height - 23 * mm, f'Получатель: {order.id_user.email}'[:60])
    address = (order.delivery_address or '—')[:120]
    c.drawString(6 * mm, height - 28 * mm, address[:60])
    c.drawString(6 * mm, height - 32 * mm, address[60:120])
    c.drawString(6 * mm, height - 37 * mm, f'Мест: 1 · Позиций: {order.items.count()}')
    barcode = code128.Code128(order.order_number, barHeight=16 * mm, barWidth=0.33 * mm)
    barcode.drawOn(c, 4 * mm, 6 * mm)
    c.showPage()
    c.save()
    return buf.getvalue()
