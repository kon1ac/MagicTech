"""Полная перезаливка витрины: чистка тестового каталога → реальные модели 2026,
студийные фото, отзывы, заказы. Staff-пользователи сохраняются.

  python manage.py seed_realistic
  python manage.py seed_realistic --orders 60
"""

from __future__ import annotations

import io
import math
import random
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.test.utils import override_settings
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

from shop.models import (
    ArchivedOrder,
    AuditLog,
    BankStatementImport,
    BankStatementLine,
    Brand,
    Cart,
    CartItem,
    Category,
    Characteristic,
    ImportJob,
    Order,
    OrderItem,
    OrderPromotion,
    Payment,
    PaymentLog,
    Price,
    Product,
    ProductImage,
    Promotion,
    PromotionBrand,
    PromotionCategory,
    PromotionProduct,
    Reservation,
    Return,
    ReturnItem,
    Review,
    Stock,
    StockMovement,
    Unit,
    Wishlist,
)
from shop.seed_data.catalog_2026 import BRAND_META, PRODUCTS, REVIEW_TEXTS
from shop.services import cart as cart_service
from shop.services import orders as order_service
from shop.services import payments as payment_service
from shop.services import pricing
from shop.services import reviews as review_service
from shop.services.catalog import invalidate_catalog_cache
from shop.services.stock import adjust_stock, receive_stock, write_off_for_order
from users.constants import ROLE_CUSTOMER
from users.models import AuthCredentials, UserProfiles

STAFF_EMAILS = {
    'admin@magtech.local', 'db@magtech.local', 'merch@magtech.local',
    'acc@magtech.local', 'picker@magtech.local', 'marketplace-bot@magtech.local',
}
CUSTOMERS = [
    ('buyer@example.com', 'Buyer123!', 'Анна', 'Покупатель'),
    ('gamer@example.com', 'Gamer123!', 'Дмитрий', 'Игроков'),
    ('office@example.com', 'Office123!', 'Елена', 'Офисная'),
    ('student@example.com', 'Student123!', 'Никита', 'Студентов'),
    ('designer@example.com', 'Design123!', 'Мария', 'Дизайнова'),
    ('stream@example.com', 'Stream123!', 'Кирилл', 'Стримов'),
]

# палитры «студии» под тип товара
PALETTES = {
    'keyboards-mech': ((28, 28, 36), (88, 70, 200), (40, 200, 220)),
    'keyboards-membrane': ((36, 36, 40), (60, 60, 70), (180, 180, 190)),
    'mice-gaming': ((20, 22, 30), (200, 40, 80), (120, 40, 200)),
    'mice-office': ((42, 44, 48), (90, 100, 110), (160, 170, 180)),
    'mousepads': ((18, 18, 22), (40, 40, 50), (100, 100, 120)),
    'headsets': ((24, 26, 34), (70, 90, 220), (220, 80, 120)),
    'webcams': ((30, 32, 38), (50, 120, 200), (90, 180, 220)),
    'usb-hubs': ((40, 42, 46), (120, 130, 140), (200, 160, 80)),
    'cables': ((32, 34, 38), (60, 70, 90), (100, 140, 180)),
    'laptop-stands': ((48, 50, 54), (140, 145, 150), (210, 210, 215)),
    'cable-organizers': ((50, 48, 46), (160, 140, 100), (220, 200, 160)),
    'chairs': ((22, 22, 26), (180, 30, 40), (40, 40, 50)),
    'cooling': ((30, 34, 40), (80, 140, 100), (160, 200, 180)),
    'thermal-paste': ((36, 36, 40), (90, 90, 100), (200, 180, 60)),
    'wipes': ((50, 52, 56), (180, 190, 200), (230, 235, 240)),
    'antistatic': ((40, 50, 70), (40, 100, 180), (80, 160, 220)),
}

CHARACTERISTICS = [
    ('connection', 'Тип подключения'), ('color', 'Цвет'), ('backlight', 'Подсветка'),
    ('material', 'Материал'), ('size', 'Размер'), ('switches', 'Переключатели'),
    ('dpi', 'Разрешение сенсора, DPI'), ('length', 'Длина кабеля'),
    ('ports', 'Количество портов'), ('resolution', 'Разрешение видео'),
]


class Command(BaseCommand):
    help = 'Чистит тестовый каталог и заливает реалистичные товары/фото/отзывы/заказы'

    def add_arguments(self, parser):
        parser.add_argument('--orders', type=int, default=55, help='Число демо-заказов')
        parser.add_argument('--orders-only', action='store_true',
                            help='Не чистить каталог — только досыпать остатки, заказы и отзывы')
        parser.add_argument('--photos-only', action='store_true',
                            help='Перерисовать силуэтные фото существующих товаров')
        parser.add_argument('--photos-stock', action='store_true',
                            help='Фото моделей через Яндекс.Картинки')
        parser.add_argument('--photos-yandex', action='store_true',
                            help='Алиас --photos-stock (Яндекс.Картинки)')
        parser.add_argument('--photos-extra', action='store_true',
                            help='Досыпать ещё 2 фото в карусель (Яндекс.Картинки)')

    def handle(self, *args, **options):
        with override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            self._run(options)

    def _run(self, options):
        rnd = random.Random(20261113)
        staff = self._users(rnd)
        self._ensure_refs()
        if options.get('photos_extra'):
            self._apply_yandex_extra_photos(extra=2)
            invalidate_catalog_cache()
            self.stdout.write(self.style.SUCCESS(
                f'Карусель: всего фото {ProductImage.objects.count()} шт.'))
            return
        if options['photos_stock'] or options.get('photos_yandex'):
            self._apply_yandex_photos()
            invalidate_catalog_cache()
            self.stdout.write(self.style.SUCCESS(
                f'Фото с Яндекса: {ProductImage.objects.count()} шт.'))
            return
        if options['photos_only']:
            self._refresh_photos()
            invalidate_catalog_cache()
            self.stdout.write(self.style.SUCCESS(
                f'Фото обновлены: {ProductImage.objects.count()} шт.'))
            return
        if options['orders_only']:
            products = list(Product.objects.filter(is_active=True))
            self.stdout.write(f'Только заказы по {len(products)} товарам…')
        else:
            self.stdout.write('Очистка торгового контура…')
            self._flush()
            self.stdout.write('Каталог и фото…')
            with transaction.atomic():
                products = self._catalog(staff['merch@magtech.local'])
            self.stdout.write(f'Товаров: {len(products)}')
        self.stdout.write('Заказы и отзывы…')
        self._orders(rnd, options['orders'], staff, products)
        invalidate_catalog_cache()
        self.stdout.write(self.style.SUCCESS(
            f'Готово: товаров {Product.objects.count()}, фото {ProductImage.objects.count()}, '
            f'заказов {Order.objects.count()}, отзывов {Review.objects.count()}.'))

    def _refresh_photos(self):
        n = 0
        for product in Product.objects.select_related('id_brand', 'id_category').prefetch_related('media'):
            cat = product.id_category.category_slug if product.id_category else ''
            brand = product.id_brand.brand_name if product.id_brand else 'MagicTech'
            for old in list(product.media.all()):
                if old.media_file:
                    old.media_file.delete(save=False)
                old.delete()
            self._attach_photo(product, cat, brand, product.product_name)
            n += 1
        self.stdout.write(f'Перерисовано карточек: {n}')

    def _apply_yandex_photos(self):
        """Реальные фото моделей из Яндекс.Картинок по названию товара."""
        import hashlib

        from shop.seed_data.yandex_photos import fetch_product_photo

        cache_dir = Path('media/_yandex_cache')
        products = list(
            Product.objects.select_related('id_category', 'id_brand')
            .prefetch_related('media')
            .order_by('id_product'))
        ok = fail = 0
        hashes: set[str] = set()

        for product in products:
            brand = product.id_brand.brand_name if product.id_brand else ''
            name = product.product_name
            query = name if brand.lower() in name.lower() else f'{brand} {name}'.strip()
            data, source = fetch_product_photo(query, cache_dir, product.product_sku)
            if data is None and query != name:
                data, source = fetch_product_photo(name, cache_dir, product.product_sku)
            if data is None:
                fail += 1
                self.stdout.write(self.style.WARNING(
                    f'  fail {product.product_sku}: {source}'))
                self.stdout.flush()
                continue
            digest = hashlib.sha256(data).hexdigest()
            if digest in hashes:
                # чуть сдвинуть яркость, чтобы файлы не совпадали 1:1
                from PIL import ImageEnhance
                img = Image.open(io.BytesIO(data)).convert('RGB')
                img = ImageEnhance.Brightness(img).enhance(1.02 + (ok % 7) * 0.01)
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=90, optimize=True)
                data = buf.getvalue()
                digest = hashlib.sha256(data).hexdigest()
            hashes.add(digest)
            for old in list(product.media.all()):
                if old.media_file:
                    old.media_file.delete(save=False)
                old.delete()
            media = ProductImage(
                id_product=product, is_main=True, sort_order=0,
                media_alt=product.product_name)
            media.media_file.save(
                f'{product.product_sku}.jpg', ContentFile(data), save=True)
            ok += 1
            short = source if len(source) < 90 else source[:87] + '...'
            self.stdout.write(f'  {product.product_sku} ← {short}')
            self.stdout.flush()
        self.stdout.write(
            f'Яндекс-фото: ок={ok}, fail={fail}, уникальных файлов={len(hashes)}')

    def _apply_yandex_extra_photos(self, extra: int = 2):
        """Ровно 1 главное + N разных доп. Дубли и лишние main вычищает."""
        import hashlib

        from shop.seed_data.yandex_photos import _norm_url, fetch_product_gallery

        cache_dir = Path('media/_yandex_cache')
        products = list(
            Product.objects.select_related('id_brand')
            .prefetch_related('media')
            .order_by('id_product'))
        added = fixed = partial = 0

        for product in products:
            existing = list(product.media.all().order_by('sort_order', 'id_media'))
            # --- главное: одно; дубли по хэшу/пути — вон ---
            main = next((m for m in existing if m.is_main), None) or (existing[0] if existing else None)
            if main is None:
                partial += 1
                self.stdout.write(self.style.WARNING(f'  {product.product_sku}: нет главного'))
                continue

            main_hash = ''
            try:
                raw = main.media_file.read() if main.media_file else b''
                if main.media_file:
                    main.media_file.close()
                main_hash = hashlib.sha256(raw).hexdigest() if raw else ''
            except Exception:
                main_hash = ''

            seen_hashes = {main_hash} if main_hash else set()
            for m in existing:
                if m.id_media == main.id_media:
                    continue
                h = ''
                try:
                    blob = m.media_file.read() if m.media_file else b''
                    if m.media_file:
                        m.media_file.close()
                    h = hashlib.sha256(blob).hexdigest() if blob else ''
                except Exception:
                    pass
                # дубль главного / повтор кадра / ошибочно main
                same_file = bool(
                    main.media_file and m.media_file
                    and main.media_file.name == m.media_file.name)
                if m.is_main or same_file or (h and h in seen_hashes):
                    if m.media_file and not same_file:
                        m.media_file.delete(save=False)
                    m.delete()
                    fixed += 1
                    continue
                if h:
                    seen_hashes.add(h)

            # перечитать и выставить флаги
            existing = list(product.media.all().order_by('sort_order', 'id_media'))
            main = next((m for m in existing if m.id_media == main.id_media), None) or existing[0]
            ProductImage.objects.filter(id_product=product).update(is_main=False)
            main.is_main = True
            main.sort_order = 0
            main.save(update_fields=['is_main', 'sort_order'])
            extras_now = [m for m in existing if m.id_media != main.id_media]
            for i, m in enumerate(extras_now, start=1):
                if m.sort_order != i or m.is_main:
                    m.sort_order = i
                    m.is_main = False
                    m.save(update_fields=['sort_order', 'is_main'])

            need = max(0, extra - len(extras_now))
            if need == 0:
                continue

            brand = product.id_brand.brand_name if product.id_brand else ''
            name = product.product_name
            query = name if brand.lower() in name.lower() else f'{brand} {name}'.strip()

            skip_urls: set[str] = set()
            main_src = cache_dir / f'{product.product_sku}.src.txt'
            if main_src.exists():
                skip_urls.add(main_src.read_text(encoding='utf-8').strip())
            for slot in range(1, 8):
                srcp = cache_dir / f'{product.product_sku}_{slot}.src.txt'
                if srcp.exists():
                    skip_urls.add(srcp.read_text(encoding='utf-8').strip())

            # сбросить кэш доп. слотов, совпадающих с главным
            for slot in range(1, extra + 3):
                cpath = cache_dir / f'{product.product_sku}_{slot}.jpg'
                if cpath.exists() and main_hash:
                    if hashlib.sha256(cpath.read_bytes()).hexdigest() == main_hash:
                        cpath.unlink(missing_ok=True)
                        (cache_dir / f'{product.product_sku}_{slot}.src.txt').unlink(missing_ok=True)

            start_slot = len(extras_now) + 1
            skip_hashes = set(seen_hashes)
            gallery = fetch_product_gallery(
                query, cache_dir, product.product_sku,
                count=need, skip_urls=skip_urls, skip_hashes=skip_hashes,
                slot_offset=start_slot)
            if len(gallery) < need and query != name:
                gallery.extend(fetch_product_gallery(
                    name, cache_dir, product.product_sku,
                    count=need - len(gallery),
                    skip_urls=skip_urls | {_norm_url(s) for _, s in gallery},
                    skip_hashes=skip_hashes,
                    slot_offset=start_slot + len(gallery)))

            got = 0
            for i, (data, source) in enumerate(gallery):
                digest = hashlib.sha256(data).hexdigest()
                if digest in seen_hashes:
                    continue
                seen_hashes.add(digest)
                order = start_slot + got
                media = ProductImage(
                    id_product=product, is_main=False, sort_order=order,
                    media_alt=f'{product.product_name} — фото {order + 1}')
                media.media_file.save(
                    f'{product.product_sku}_{order}.jpg', ContentFile(data), save=True)
                # на всякий: главное только одно
                if media.is_main:
                    media.is_main = False
                    media.save(update_fields=['is_main'])
                added += 1
                got += 1
                short = source if len(source) < 80 else source[:77] + '...'
                self.stdout.write(f'  {product.product_sku} +{order} ← {short}')
                self.stdout.flush()
                if got >= need:
                    break
            if got < need:
                partial += 1
                self.stdout.write(self.style.WARNING(
                    f'  {product.product_sku}: доп. {got}/{need}'))
                self.stdout.flush()

        # финальный проход: ровно один is_main на товар
        for product in Product.objects.prefetch_related('media'):
            imgs = list(product.media.all().order_by('sort_order', 'id_media'))
            if not imgs:
                continue
            keep = next((m for m in imgs if m.is_main), imgs[0])
            ProductImage.objects.filter(id_product=product).exclude(
                id_media=keep.id_media).update(is_main=False)
            if not keep.is_main or keep.sort_order != 0:
                keep.is_main = True
                keep.sort_order = 0
                keep.save(update_fields=['is_main', 'sort_order'])

        self.stdout.write(
            f'Доп. фото: добавлено={added}, снято дублей/лишних main={fixed}, недобрали={partial}')

    # ------------------------------------------------------------------ flush
    def _flush(self):
        # порядок с учётом FK
        for model in (
            BankStatementLine, BankStatementImport, PaymentLog, ReturnItem, Return,
            Review, Wishlist, OrderPromotion, OrderItem, Reservation, StockMovement,
            Payment, Order, ArchivedOrder, CartItem, Cart, Stock, Price, ProductImage,
            PromotionProduct, PromotionCategory, PromotionBrand, Promotion,
            ImportJob, AuditLog,
        ):
            model.objects.all().delete()
        Product.objects.all().delete()
        Brand.objects.all().delete()
        # медиафайлы старых товаров
        media = Path('media/products')
        if media.exists():
            for f in media.glob('*'):
                if f.is_file():
                    try:
                        f.unlink()
                    except OSError:
                        pass

    def _users(self, rnd):
        from users.constants import (
            ROLE_ACCOUNTANT as RA, ROLE_ADMIN as RAD, ROLE_DB_ADMIN as RD,
            ROLE_MERCHANDISER as RM, ROLE_PICKER as RP,
        )
        staff_defs = [
            ('admin@magtech.local', RAD, 'Admin123!', 'Алексей', 'Системов'),
            ('db@magtech.local', RD, 'DbAdmin123!', 'Мария', 'Данилова'),
            ('merch@magtech.local', RM, 'Merch123!', 'Иван', 'Каталогов'),
            ('acc@magtech.local', RA, 'Acc123!', 'Ольга', 'Финова'),
            ('picker@magtech.local', RP, 'Pick123!', 'Пётр', 'Складов'),
            ('marketplace-bot@magtech.local', RAD, 'Service123!', 'Сервис', 'Маркетплейсы'),
        ]
        result = {}
        for email, role, pwd, fn, ln in staff_defs:
            user, created = AuthCredentials.objects.get_or_create(email=email, defaults={'user_role': role})
            if created or not user.check_password(pwd):
                user.set_password(pwd)
            user.user_role, user.is_active = role, True
            user.save()
            UserProfiles.objects.get_or_create(
                id_user=user, defaults={'profile_first_name': fn, 'profile_last_name': ln})
            result[email] = user
        for email, pwd, fn, ln in CUSTOMERS:
            user, created = AuthCredentials.objects.get_or_create(
                email=email, defaults={'user_role': ROLE_CUSTOMER})
            if created or not user.check_password(pwd):
                user.set_password(pwd)
                user.save()
            UserProfiles.objects.update_or_create(
                id_user=user,
                defaults={
                    'profile_first_name': fn, 'profile_last_name': ln,
                    'profile_phone': f'+7 900 {rnd.randint(100,999)}-{rnd.randint(10,99)}-{rnd.randint(10,99)}',
                    'profile_address': (
                        f'г. Москва, ул. Профсоюзная, д. {rnd.randint(1,120)}, '
                        f'кв. {rnd.randint(1,300)}'),
                })
            result[email] = user
        return result

    def _ensure_refs(self):
        for code, name in CHARACTERISTICS:
            Characteristic.objects.get_or_create(char_code=code, defaults={'char_name': name})
        Unit.objects.get_or_create(unit_code='pcs', defaults={'unit_name': 'шт.'})

    # ------------------------------------------------------------------ catalog
    def _catalog(self, merch):
        pcs = Unit.objects.filter(unit_code='pcs').first()
        brands = {}
        for name, desc in BRAND_META.items():
            brands[name], _ = Brand.objects.get_or_create(
                brand_slug=slugify(name) or name.lower(),
                defaults={'brand_name': name, 'brand_description': desc, 'is_active': True})
            Brand.objects.filter(pk=brands[name].pk).update(
                brand_name=name, brand_description=desc, is_active=True)

        cats = {c.category_slug: c for c in Category.objects.all()}
        missing = sorted({p[3] for p in PRODUCTS} - set(cats))
        if missing:
            raise RuntimeError(f'Нет категорий: {missing}. Сначала seed_magtech или создайте дерево.')

        products = []
        for sku, name, brand, cat_slug, price, cost, stock_qty, ean, chars, desc in PRODUCTS:
            product = Product.objects.create(
                product_sku=sku,
                product_ean=ean,
                product_name=name,
                id_brand=brands[brand],
                id_category=cats[cat_slug],
                id_unit=pcs,
                product_description=desc,
                product_characteristics=chars,
                cost_price=Decimal(cost),
                seo_title=f'Купить {name} — MagicTech',
                seo_description=f'{name}: актуальная цена, доставка по России, оплата картой. {desc[:140]}',
                seo_keywords=f'{brand}, {name}, купить, MagicTech',
                is_active=True,
                sales_count=0,
            )
            pricing.set_price(product, Decimal(price), actor=merch, reason='Прайс 2026')
            Stock.objects.create(
                id_product=product, stock_quantity=stock_qty, stock_reserved=0,
                stock_movement_type='receipt')
            self._attach_photo(product, cat_slug, brand, name)
            products.append(product)
        return products

    def _attach_photo(self, product, cat_slug, brand, name):
        img = self._render_photo(cat_slug, brand, name)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=88, optimize=True)
        buf.seek(0)
        media = ProductImage(id_product=product, is_main=True, sort_order=0, media_alt=name)
        media.media_file.save(f'{product.product_sku}.jpg', ContentFile(buf.read()), save=True)

    def _render_photo(self, cat_slug, brand, name):
        """Студийный кадр: светлый фон + силуэт типа товара (не абстрактные кольца)."""
        w, h = 900, 675
        # светлая «фотостудия»
        img = Image.new('RGB', (w, h), (244, 246, 250))
        draw = ImageDraw.Draw(img)
        for y in range(h):
            t = y / h
            col = (
                int(244 - 18 * t),
                int(246 - 16 * t),
                int(250 - 12 * t),
            )
            draw.line([(0, y), (w, y)], fill=col)
        # мягкая тень-эллипс под товаром
        draw.ellipse((210, 520, 690, 600), fill=(210, 214, 222))
        accent = PALETTES.get(cat_slug, ((40, 42, 50), (90, 100, 140), (160, 170, 190)))[1]
        body = (32, 34, 40)
        hi = (70, 74, 84)
        kind = cat_slug or ''
        if 'keyboard' in kind:
            self._draw_keyboard(draw, body, hi, accent)
        elif 'mice' in kind or kind == 'mice-gaming' or kind == 'mice-office':
            self._draw_mouse(draw, body, hi, accent)
        elif 'headset' in kind or 'headphone' in kind:
            self._draw_headset(draw, body, hi, accent)
        elif 'webcam' in kind:
            self._draw_webcam(draw, body, hi, accent)
        elif 'mousepad' in kind:
            self._draw_mousepad(draw, body, accent)
        elif 'chair' in kind:
            self._draw_chair(draw, body, hi, accent)
        elif 'hub' in kind:
            self._draw_hub(draw, body, hi, accent)
        elif 'cable-organizer' in kind or 'organizer' in kind:
            self._draw_hub(draw, body, hi, accent)
        elif 'cable' in kind:
            self._draw_cable(draw, body, accent)
        elif 'thermal' in kind:
            self._draw_thermal(draw, body, hi, accent)
        elif 'cooling' in kind:
            self._draw_cooler(draw, body, hi, accent)
        elif 'wipe' in kind:
            self._draw_wipes(draw, body, hi, accent)
        elif 'antistatic' in kind:
            self._draw_esd(draw, body, hi, accent)
        else:
            self._draw_box(draw, body, hi, accent)
        try:
            font_b = ImageFont.truetype('arialbd.ttf', 28)
            font_n = ImageFont.truetype('arial.ttf', 20)
            font_s = ImageFont.truetype('arial.ttf', 15)
        except OSError:
            try:
                font_b = ImageFont.truetype('arial.ttf', 28)
                font_n = ImageFont.truetype('arial.ttf', 20)
                font_s = ImageFont.truetype('arial.ttf', 15)
            except OSError:
                font_b = font_n = font_s = ImageFont.load_default()
        draw.text((36, 28), brand, fill=(40, 44, 55), font=font_b)
        words = name.split()
        line1, line2 = ' '.join(words[:5]), ' '.join(words[5:])
        draw.text((36, 610), line1[:48], fill=(30, 34, 42), font=font_n)
        if line2:
            draw.text((36, 638), line2[:48], fill=(100, 108, 120), font=font_s)
        draw.text((w - 150, 28), 'MagicTech', fill=(140, 148, 160), font=font_s)
        return img

    def _draw_keyboard(self, d, body, hi, accent):
        d.rounded_rectangle((140, 230, 760, 430), radius=18, fill=body, outline=hi, width=2)
        # клавиши
        x0, y0 = 165, 255
        for row in range(5):
            for col in range(14):
                x = x0 + col * 40
                y = y0 + row * 32
                if x > 720:
                    continue
                fill = accent if (row == 0 and col in (0, 13)) or (row == 4 and 4 <= col <= 9) else (48, 52, 60)
                d.rounded_rectangle((x, y, x + 34, y + 26), radius=4, fill=fill)

    def _draw_mouse(self, d, body, hi, accent):
        d.ellipse((320, 180, 580, 520), fill=body, outline=hi, width=2)
        d.line((450, 210, 450, 360), fill=hi, width=3)
        d.rounded_rectangle((430, 300, 470, 360), radius=8, fill=accent)
        d.ellipse((400, 230, 430, 270), fill=hi)
        d.ellipse((470, 230, 500, 270), fill=hi)

    def _draw_headset(self, d, body, hi, accent):
        d.arc((250, 140, 650, 420), 200, 340, fill=body, width=28)
        d.rounded_rectangle((240, 280, 330, 420), radius=30, fill=body, outline=hi, width=2)
        d.rounded_rectangle((570, 280, 660, 420), radius=30, fill=body, outline=hi, width=2)
        d.ellipse((255, 310, 315, 390), fill=accent)
        d.ellipse((585, 310, 645, 390), fill=accent)
        d.line((300, 400, 380, 520), fill=hi, width=6)
        d.ellipse((360, 500, 420, 560), fill=body)

    def _draw_webcam(self, d, body, hi, accent):
        d.rounded_rectangle((300, 200, 600, 380), radius=40, fill=body, outline=hi, width=2)
        d.ellipse((360, 230, 540, 360), fill=(20, 22, 28), outline=accent, width=4)
        d.ellipse((410, 265, 490, 325), fill=accent)
        d.rectangle((420, 380, 480, 470), fill=hi)
        d.ellipse((390, 460, 510, 500), fill=body)

    def _draw_mousepad(self, d, body, accent):
        d.rounded_rectangle((160, 200, 740, 480), radius=16, fill=body)
        d.rounded_rectangle((180, 220, 720, 460), radius=12, fill=(24, 26, 32))
        d.arc((200, 240, 400, 400), 30, 200, fill=accent, width=3)

    def _draw_chair(self, d, body, hi, accent):
        d.rounded_rectangle((340, 150, 560, 280), radius=40, fill=body)
        d.rounded_rectangle((300, 270, 600, 420), radius=24, fill=body, outline=hi, width=2)
        d.rectangle((430, 420, 470, 500), fill=hi)
        d.ellipse((360, 490, 540, 540), fill=body)
        d.rectangle((310, 290, 340, 400), fill=accent)
        d.rectangle((560, 290, 590, 400), fill=accent)

    def _draw_hub(self, d, body, hi, accent):
        d.rounded_rectangle((260, 250, 640, 390), radius=20, fill=body, outline=hi, width=2)
        for i, x in enumerate((300, 380, 460, 540)):
            d.rounded_rectangle((x, 290, x + 50, 350), radius=6, fill=(20, 22, 28), outline=accent if i == 0 else hi, width=2)

    def _draw_cable(self, d, body, accent):
        d.line((200, 320, 700, 320), fill=accent, width=10)
        d.rounded_rectangle((170, 290, 230, 350), radius=8, fill=body)
        d.rounded_rectangle((670, 290, 730, 350), radius=8, fill=body)
        d.ellipse((250, 300, 310, 340), fill=body)
        d.ellipse((590, 300, 650, 340), fill=body)

    def _draw_cooler(self, d, body, hi, accent):
        d.rounded_rectangle((300, 180, 600, 480), radius=16, fill=body, outline=hi, width=2)
        d.ellipse((340, 220, 560, 440), fill=(22, 24, 30), outline=accent, width=6)
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            x1, y1 = 450 + int(40 * math.cos(rad)), 330 + int(40 * math.sin(rad))
            x2, y2 = 450 + int(90 * math.cos(rad)), 330 + int(90 * math.sin(rad))
            d.line((x1, y1, x2, y2), fill=hi, width=8)
        d.ellipse((420, 300, 480, 360), fill=accent)

    def _draw_box(self, d, body, hi, accent):
        d.rounded_rectangle((280, 200, 620, 460), radius=24, fill=body, outline=hi, width=2)
        d.rounded_rectangle((320, 240, 580, 420), radius=16, fill=(24, 26, 32), outline=accent, width=3)

    def _draw_thermal(self, d, body, hi, accent):
        # тюбик термопасты
        d.rounded_rectangle((380, 160, 520, 480), radius=28, fill=body, outline=hi, width=2)
        d.polygon([(390, 160), (450, 90), (510, 160)], fill=hi)
        d.rounded_rectangle((400, 220, 500, 300), radius=10, fill=accent)
        d.ellipse((420, 400, 480, 460), fill=(240, 240, 245))

    def _draw_wipes(self, d, body, hi, accent):
        # пачка салфеток + флакон
        d.rounded_rectangle((250, 240, 520, 460), radius=18, fill=(235, 238, 244), outline=hi, width=2)
        d.rounded_rectangle((270, 260, 500, 320), radius=10, fill=accent)
        d.rounded_rectangle((560, 200, 680, 460), radius=40, fill=body, outline=hi, width=2)
        d.ellipse((580, 170, 660, 230), fill=hi)
        d.rounded_rectangle((590, 280, 650, 360), radius=8, fill=accent)

    def _draw_esd(self, d, body, hi, accent):
        # антистатический браслет
        d.arc((280, 220, 620, 480), 20, 340, fill=accent, width=22)
        d.rounded_rectangle((300, 300, 420, 400), radius=16, fill=body, outline=hi, width=2)
        d.rounded_rectangle((360, 330, 560, 370), radius=8, fill=(40, 120, 200))
        d.line((560, 350, 720, 420), fill=(180, 180, 190), width=4)

    # ------------------------------------------------------------------ orders
    def _orders(self, rnd, count, staff, products):
        admin, picker = staff['admin@magtech.local'], staff['picker@magtech.local']
        customers = [staff[c[0]] for c in CUSTOMERS]
        for product in products:
            receive_stock(product, 250, actor=picker, document_number='ПН-2026-001', reason='Поступление 2026')

        finals = (
            ['COMPLETED'] * 40 + ['PACKED'] * 5 + ['ASSEMBLY'] * 4 + ['CONFIRMED'] * 4
            + ['PAID'] * 3 + ['NEW'] * 3 + ['CANCELLED'] * 6)
        created = 0
        fail_reasons = {}
        for _ in range(count):
            user = rnd.choice(customers)
            cart = cart_service.get_cart(user=user)
            try:
                cart_service.clear(cart)
            except Exception:
                cart.items.all().delete()
            sample = rnd.sample(products, k=min(len(products), rnd.randint(1, 3)))
            for product in sample:
                try:
                    cart_service.add_item(cart, product, rnd.randint(1, 2))
                except Exception as exc:
                    key = type(exc).__name__
                    fail_reasons[key] = fail_reasons.get(key, 0) + 1
                    continue
            cart.refresh_from_db()
            if not cart.items.exists():
                continue
            method = 'card_online' if rnd.random() < 0.72 else 'cash_on_delivery'
            profile = getattr(user, 'profile', None)
            # PII в профиле зашифровано (Fernet) — в заказ только plaintext
            if profile is not None:
                address = (profile.get_plain('profile_address') or 'г. Москва')[:500]
                phone = (profile.get_plain('profile_phone') or '+79000000000')[:30]
            else:
                address, phone = 'г. Москва', '+79000000000'
            try:
                order, payment = order_service.checkout(
                    cart, user=user, payment_method=method, offer_accepted=True,
                    delivery_address=address, contact_phone=phone)
            except Exception as exc:
                key = f'checkout:{type(exc).__name__}'
                fail_reasons[key] = fail_reasons.get(key, 0) + 1
                if fail_reasons[key] <= 2:
                    self.stdout.write(self.style.WARNING(f'checkout: {exc}'))
                try:
                    cart_service.clear(cart)
                except Exception:
                    pass
                continue
            try:
                final = rnd.choice(finals)
                self._advance(order, payment, final, admin, picker)
                back = timezone.now() - timedelta(days=rnd.randint(0, 100), hours=rnd.randint(0, 23))
                Order.objects.filter(pk=order.pk).update(
                    created_at=back, updated_at=back + timedelta(hours=rnd.randint(1, 48)))
                Order.objects.filter(pk=order.pk, paid_at__isnull=False).update(
                    paid_at=back + timedelta(minutes=8))
                order.payments.update(created_at=back)
                order.payments.filter(paid_at__isnull=False).update(paid_at=back + timedelta(minutes=8))
                created += 1
                order.refresh_from_db()
                if order.order_status == 'COMPLETED':
                    for item in order.items.all():
                        if rnd.random() < 0.55:
                            rating = rnd.choice([5, 5, 5, 4, 4, 4, 3, 3, 2])
                            try:
                                review = review_service.create_review(
                                    user, item.id_product, rating=rating,
                                    text=rnd.choice(REVIEW_TEXTS[rating]))
                                review_service.moderate(review, 'approved', actor=admin)
                            except Exception:
                                pass
            except Exception as exc:
                key = f'advance:{type(exc).__name__}'
                fail_reasons[key] = fail_reasons.get(key, 0) + 1
                if fail_reasons[key] <= 2:
                    self.stdout.write(self.style.WARNING(f'advance: {exc}'))
        # реалистичные остатки: не обнуляем витрину
        for stock in Stock.objects.select_related('id_product'):
            target = max(stock.stock_reserved + 5, stock.stock_reserved + rnd.choice([5, 8, 12, 18, 25, 40, 55]))
            delta = target - stock.stock_quantity
            if delta:
                try:
                    adjust_stock(stock.id_product, delta, actor=admin, reason='Инвентаризация после сида')
                except Exception:
                    pass
        for p in Product.objects.all():
            reviews = list(Review.objects.filter(
                id_product=p, review_type='review', review_status='approved',
                review_rating__isnull=False))
            if reviews:
                avg = sum(r.review_rating for r in reviews) / len(reviews)
                Product.objects.filter(pk=p.pk).update(
                    rating_avg=Decimal(str(round(avg, 2))), rating_count=len(reviews))
            sold = sum(OrderItem.objects.filter(
                id_order__order_status='COMPLETED', id_product=p
            ).values_list('order_item_quantity', flat=True)) or 0
            Product.objects.filter(pk=p.pk).update(sales_count=sold)
        self.stdout.write(f'Создано заказов: {created}')
        if fail_reasons:
            self.stdout.write(f'Пропуски: {fail_reasons}')

    def _advance(self, order, payment, final, admin, picker):
        if final == 'NEW':
            return
        if final == 'CANCELLED':
            order_service.change_order_status(
                order, 'CANCELLED', actor=admin, reason='Отмена покупателем')
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
