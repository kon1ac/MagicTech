"""PDF счёт / накладная по завершённому заказу (reportlab)."""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


_FONT = 'Helvetica'
_FONT_BOLD = 'Helvetica-Bold'


def _register_fonts() -> None:
    global _FONT, _FONT_BOLD
    candidates = [
        (Path(r'C:\Windows\Fonts\arial.ttf'), Path(r'C:\Windows\Fonts\arialbd.ttf')),
        (Path(r'C:\Windows\Fonts\segoeui.ttf'), Path(r'C:\Windows\Fonts\segoeuib.ttf')),
        (Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
         Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')),
    ]
    for regular, bold in candidates:
        if regular.exists():
            try:
                pdfmetrics.registerFont(TTFont('MTSans', str(regular)))
                if bold.exists():
                    pdfmetrics.registerFont(TTFont('MTSans-Bold', str(bold)))
                    _FONT_BOLD = 'MTSans-Bold'
                else:
                    _FONT_BOLD = 'MTSans'
                _FONT = 'MTSans'
                return
            except Exception:
                continue


_register_fonts()


def build_order_invoice(order) -> bytes:
    """Возвращает PDF-байты счёта-накладной."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f'Счёт-накладная {order.order_number}',
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        'MTTitle', parent=styles['Heading1'], fontName=_FONT_BOLD,
        fontSize=16, alignment=TA_CENTER, spaceAfter=8, textColor=colors.HexColor('#111827'),
    )
    h2 = ParagraphStyle(
        'MTH2', parent=styles['Normal'], fontName=_FONT_BOLD,
        fontSize=11, spaceBefore=10, spaceAfter=4,
    )
    body = ParagraphStyle(
        'MTBody', parent=styles['Normal'], fontName=_FONT,
        fontSize=9, leading=13,
    )
    right = ParagraphStyle('MTRight', parent=body, alignment=TA_RIGHT)
    small = ParagraphStyle('MTSmall', parent=body, fontSize=8, textColor=colors.HexColor('#4b5563'))

    story = []
    story.append(Paragraph('MagicTech — счёт / накладная', title))
    story.append(Paragraph(
        f'Заказ <b>{order.order_number}</b> · от {order.created_at.strftime("%d.%m.%Y %H:%M")} · статус: завершён',
        ParagraphStyle('MTSub', parent=body, alignment=TA_CENTER),
    ))
    story.append(Spacer(1, 8))

    story.append(Paragraph('Продавец', h2))
    story.append(Paragraph(
        'MagicTech · интернет-магазин аксессуаров для ПК<br/>'
        'Оплата картой через ЮKassa · гарантия и возврат 14 дней',
        body,
    ))

    story.append(Paragraph('Покупатель и доставка', h2))
    phone = order.contact_phone or '—'
    addr = (order.delivery_address or '—').replace('\n', '<br/>')
    email = getattr(getattr(order, 'id_user', None), 'email', '') or '—'
    story.append(Paragraph(
        f'Email: {email}<br/>Телефон: {phone}<br/>Адрес: {addr}',
        body,
    ))

    story.append(Paragraph('Позиции', h2))
    rows = [[
        Paragraph('<b>№</b>', body),
        Paragraph('<b>Товар / артикул</b>', body),
        Paragraph('<b>Цена</b>', right),
        Paragraph('<b>Кол-во</b>', right),
        Paragraph('<b>Скидка</b>', right),
        Paragraph('<b>Сумма</b>', right),
    ]]
    for i, item in enumerate(order.items.select_related('id_product').all(), start=1):
        p = item.id_product
        name = f'{p.product_name}<br/><font size="7" color="#6b7280">{p.product_sku}</font>'
        rows.append([
            Paragraph(str(i), body),
            Paragraph(name, body),
            Paragraph(f'{item.order_item_price:.2f}', right),
            Paragraph(str(item.order_item_quantity), right),
            Paragraph(f'{item.order_item_discount:.2f}' if item.order_item_discount else '—', right),
            Paragraph(f'{item.order_item_total:.2f}', right),
        ])

    table = Table(rows, colWidths=[12 * mm, 88 * mm, 22 * mm, 18 * mm, 20 * mm, 24 * mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2ff')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d1d5db')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    story.append(Spacer(1, 8))

    totals = [
        [Paragraph('Подытог', body), Paragraph(f'{order.subtotal:.2f} ₽', right)],
        [Paragraph('Скидка', body), Paragraph(f'−{order.discount_total:.2f} ₽', right)],
        [Paragraph('<b>Итого к оплате</b>', body), Paragraph(f'<b>{order.total:.2f} ₽</b>', right)],
    ]
    t2 = Table(totals, colWidths=[140 * mm, 40 * mm])
    t2.setStyle(TableStyle([
        ('LINEABOVE', (0, -1), (-1, -1), 0.8, colors.HexColor('#111827')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t2)
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        'Документ сформирован автоматически для завершённого заказа. '
        'Храните PDF для гарантии и возврата.',
        small,
    ))
    story.append(Paragraph('MagicTech · magtech.local', small))

    doc.build(story)
    return buf.getvalue()
