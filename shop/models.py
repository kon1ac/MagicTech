import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from users.models import AuthCredentials


class Unit(models.Model):
    """Справочник единиц измерения (таблица units)."""

    id_unit = models.BigAutoField(primary_key=True)
    unit_code = models.CharField(max_length=20, unique=True)
    unit_name = models.CharField(max_length=100)

    class Meta:
        db_table = 'units'
        verbose_name = 'Единица измерения'
        verbose_name_plural = 'Единицы измерения'

    def __str__(self):
        return self.unit_name


class OrderStatusRef(models.Model):
    """Справочник статусов заказа (таблица order_statuses)."""

    status_code = models.CharField(max_length=20, primary_key=True)
    status_label = models.CharField(max_length=100)
    sort_order = models.SmallIntegerField(default=0)
    is_final = models.BooleanField(default=False)

    class Meta:
        db_table = 'order_statuses'
        ordering = ['sort_order']
        verbose_name = 'Статус заказа'
        verbose_name_plural = 'Статусы заказов'

    def __str__(self):
        return self.status_label


class ReturnReason(models.Model):
    """Справочник причин возврата (таблица return_reasons)."""

    id_reason = models.BigAutoField(primary_key=True)
    reason_code = models.CharField(max_length=30, unique=True)
    reason_name = models.CharField(max_length=255)
    is_defect = models.BooleanField(default=False)

    class Meta:
        db_table = 'return_reasons'
        verbose_name = 'Причина возврата'
        verbose_name_plural = 'Причины возврата'

    def __str__(self):
        return self.reason_name


class PromotionTypeRef(models.Model):
    """Справочник типов акций (таблица promotion_types)."""

    type_code = models.CharField(max_length=20, primary_key=True)
    type_name = models.CharField(max_length=100)

    class Meta:
        db_table = 'promotion_types'
        verbose_name = 'Тип акции'
        verbose_name_plural = 'Типы акций'

    def __str__(self):
        return self.type_name


class Category(models.Model):
    """Категория товаров (таблица categories)."""

    id_category = models.BigAutoField(primary_key=True)
    id_parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='id_parent',
        related_name='children',
    )
    category_name = models.CharField(max_length=255)
    category_slug = models.SlugField(max_length=255, unique=True, blank=True, null=True)
    category_level = models.SmallIntegerField()
    category_attributes = models.JSONField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'categories'
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    def __str__(self):
        return self.category_name

    def ancestors(self):
        node, chain = self, []
        while node is not None:
            chain.append(node)
            node = node.id_parent
        return list(reversed(chain))

    def descendant_ids(self):
        ids, frontier = [self.pk], [self.pk]
        while frontier:
            frontier = list(
                Category.objects.filter(id_parent__in=frontier).values_list('pk', flat=True)
            )
            ids.extend(frontier)
        return ids


class Characteristic(models.Model):
    """Справочник характеристик товаров (таблица characteristics)."""

    VALUE_TYPES = [('str', 'Строка'), ('num', 'Число'), ('bool', 'Да/нет')]

    id_characteristic = models.BigAutoField(primary_key=True)
    char_code = models.SlugField(max_length=50, unique=True)
    char_name = models.CharField(max_length=100)
    char_value_type = models.CharField(max_length=10, choices=VALUE_TYPES, default='str')
    id_unit = models.ForeignKey(
        Unit, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_unit'
    )
    is_filterable = models.BooleanField(default=True)
    sort_order = models.SmallIntegerField(default=0)

    class Meta:
        db_table = 'characteristics'
        ordering = ['sort_order', 'char_name']
        verbose_name = 'Характеристика'
        verbose_name_plural = 'Характеристики'

    def __str__(self):
        return self.char_name


class Brand(models.Model):
    """Бренд (таблица brands)."""

    id_brand = models.BigAutoField(primary_key=True)
    brand_name = models.CharField(max_length=255)
    brand_slug = models.SlugField(max_length=255, unique=True, blank=True, null=True)
    brand_description = models.TextField(blank=True, null=True)
    brand_logo_url = models.ImageField(
        upload_to='brands/',
        max_length=500,
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'brands'
        verbose_name = 'Бренд'
        verbose_name_plural = 'Бренды'

    def __str__(self):
        return self.brand_name


class Product(models.Model):
    """Товар (таблица products)."""

    id_product = models.BigAutoField(primary_key=True)
    product_sku = models.CharField(max_length=100, unique=True)
    product_ean = models.CharField(max_length=50, unique=True, blank=True, null=True)
    product_name = models.CharField(max_length=255)
    id_brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='id_brand',
        related_name='products',
    )
    id_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='id_category',
        related_name='products',
    )
    product_description = models.TextField(blank=True, null=True)
    product_characteristics = models.JSONField(blank=True, null=True)
    product_images = models.JSONField(blank=True, null=True)
    id_unit = models.ForeignKey(
        Unit, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_unit'
    )
    seo_title = models.CharField(max_length=255, blank=True, null=True)
    seo_description = models.CharField(max_length=500, blank=True, null=True)
    seo_keywords = models.CharField(max_length=500, blank=True, null=True)
    cost_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.IntegerField(default=0)
    sales_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        indexes = [
            models.Index(fields=['is_active', 'id_category'], name='products_active_cat_idx'),
            models.Index(fields=['id_brand'], name='products_brand_idx'),
            models.Index(fields=['-sales_count'], name='products_popularity_idx'),
            models.Index(fields=['-created_at'], name='products_created_idx'),
            models.Index(fields=['-rating_avg'], name='products_rating_idx'),
        ]

    def __str__(self):
        return f'{self.product_sku} — {self.product_name}'

    @property
    def current_price(self):
        price = self.prices.filter(valid_to__isnull=True).order_by('-valid_from').first()
        return price.product_price if price else None

    @property
    def main_image(self):
        images = sorted(self.media.all(), key=lambda m: (not m.is_main, m.sort_order))
        return images[0].url if images else None


class ProductImage(models.Model):
    """Изображения товара, множественные фото (таблица product_media)."""

    id_media = models.BigAutoField(primary_key=True)
    id_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, db_column='id_product', related_name='media'
    )
    media_file = models.ImageField(upload_to='products/', max_length=500, blank=True, null=True)
    media_url = models.URLField(max_length=500, blank=True, null=True)
    media_alt = models.CharField(max_length=255, blank=True, null=True)
    sort_order = models.SmallIntegerField(default=0)
    is_main = models.BooleanField(default=False)

    class Meta:
        db_table = 'product_media'
        ordering = ['sort_order']
        verbose_name = 'Изображение товара'
        verbose_name_plural = 'Изображения товаров'

    @property
    def url(self):
        if self.media_file:
            return self.media_file.url
        return self.media_url


class Price(models.Model):
    """Цена товара (таблица prices)."""

    id_price = models.BigAutoField(primary_key=True)
    id_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        db_column='id_product',
        related_name='prices',
    )
    product_price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    price_currency = models.CharField(max_length=3, default='RUB')
    price_reason = models.CharField(max_length=255, blank=True, null=True)
    valid_from = models.DateTimeField(auto_now_add=True)
    valid_to = models.DateTimeField(blank=True, null=True)
    id_user = models.ForeignKey(
        AuthCredentials,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='id_user',
        related_name='prices_set',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'prices'
        indexes = [models.Index(fields=['id_product', 'valid_to'], name='prices_current_idx')]
        constraints = [
            models.CheckConstraint(condition=models.Q(product_price__gte=0), name='prices_non_negative'),
        ]
        verbose_name = 'Цена'
        verbose_name_plural = 'Цены'

    def __str__(self):
        return f'{self.id_product}: {self.product_price} {self.price_currency}'


class Promotion(models.Model):
    """Акция (таблица promotions)."""

    id_promotion = models.BigAutoField(primary_key=True)
    promotion_name = models.CharField(max_length=255)
    promotion_type = models.CharField(max_length=20)
    promotion_value = models.DecimalField(max_digits=12, decimal_places=2)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    promotion_promo_code = models.CharField(max_length=50, blank=True, null=True, unique=True)
    promotion_description = models.TextField(blank=True, null=True)
    promotion_min_sum = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    promotion_min_qty = models.IntegerField(default=0)
    usage_limit = models.IntegerField(blank=True, null=True)
    usage_count = models.IntegerField(default=0)
    is_stackable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    id_user = models.ForeignKey(
        AuthCredentials,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='id_user',
        related_name='promotions_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promotions'
        verbose_name = 'Акция'
        verbose_name_plural = 'Акции'

    def __str__(self):
        return self.promotion_name


class Stock(models.Model):
    """Остатки на складе (таблица stock)."""

    id_stock = models.BigAutoField(primary_key=True)
    id_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        db_column='id_product',
        related_name='stock_records',
    )
    stock_quantity = models.IntegerField(default=0)
    stock_reserved = models.IntegerField(default=0)
    stock_movement_type = models.CharField(max_length=20, blank=True, null=True)
    stock_movement_history = models.JSONField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stock'
        constraints = [
            models.UniqueConstraint(fields=['id_product'], name='stock_one_per_product'),
            models.CheckConstraint(condition=models.Q(stock_quantity__gte=0), name='stock_quantity_non_negative'),
            models.CheckConstraint(condition=models.Q(stock_reserved__gte=0), name='stock_reserved_non_negative'),
        ]
        verbose_name = 'Остаток'
        verbose_name_plural = 'Остатки'

    def __str__(self):
        return f'{self.id_product}: {self.stock_quantity} шт.'

    @property
    def available_quantity(self) -> int:
        return self.stock_quantity - self.stock_reserved


class Cart(models.Model):
    """Корзина (таблица carts)."""

    id_cart = models.BigAutoField(primary_key=True)
    id_user = models.ForeignKey(
        AuthCredentials,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='id_user',
        related_name='carts',
    )
    cart_session_id = models.CharField(max_length=100, blank=True, null=True)
    cart_status = models.CharField(max_length=20, default='active')
    cart_promo_code = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'carts'
        verbose_name = 'Корзина'
        verbose_name_plural = 'Корзины'

    def __str__(self):
        owner = self.id_user.email if self.id_user else self.cart_session_id
        return f'Корзина #{self.id_cart} ({owner})'


class Order(models.Model):
    """Заказ (таблица orders)."""

    id_order = models.BigAutoField(primary_key=True)
    order_number = models.CharField(max_length=50, unique=True)
    id_user = models.ForeignKey(
        AuthCredentials,
        on_delete=models.RESTRICT,
        db_column='id_user',
        related_name='orders',
    )
    order_status = models.CharField(max_length=20, default='NEW')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    order_payment_method = models.CharField(max_length=30, blank=True, null=True)
    order_payment_status = models.CharField(max_length=20, blank=True, null=True)
    order_channel = models.CharField(max_length=20, default='site')
    external_order_id = models.CharField(max_length=100, blank=True, null=True)
    order_promo_code = models.CharField(max_length=50, blank=True, null=True)
    order_comment = models.TextField(blank=True, null=True)
    delivery_address = models.TextField(blank=True, null=True)
    contact_phone = models.CharField(max_length=30, blank=True, null=True)
    offer_accepted = models.BooleanField(default=False)
    payment_due_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    shipped_at = models.DateTimeField(blank=True, null=True)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders'
        indexes = [
            models.Index(fields=['order_status', '-created_at'], name='orders_status_created_idx'),
            models.Index(fields=['id_user', '-created_at'], name='orders_user_created_idx'),
        ]
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    def __str__(self):
        return self.order_number


class Payment(models.Model):
    """Платёж (таблица payments)."""

    id_payment = models.BigAutoField(primary_key=True)
    id_order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        db_column='id_order',
        related_name='payments',
    )
    payment_uid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    external_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    payment_provider = models.CharField(max_length=30)
    payment_method = models.CharField(max_length=30, blank=True, null=True)
    payment_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_requisites = models.JSONField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    payment_amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_currency = models.CharField(max_length=3, default='RUB')
    payment_status = models.CharField(max_length=20, default='PENDING')
    payment_refund_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
    )
    id_user = models.ForeignKey(
        AuthCredentials,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='id_user',
        related_name='payments',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments'
        verbose_name = 'Платёж'
        verbose_name_plural = 'Платежи'

    def __str__(self):
        return f'Платёж #{self.id_payment} — {self.payment_amount} {self.payment_currency}'


class Return(models.Model):
    """Возврат (таблица returns)."""

    id_return = models.BigAutoField(primary_key=True)
    id_order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        db_column='id_order',
        related_name='returns',
    )
    id_user = models.ForeignKey(
        AuthCredentials,
        on_delete=models.RESTRICT,
        db_column='id_user',
        related_name='returns',
    )
    return_reason = models.CharField(max_length=255, blank=True, null=True)
    id_reason = models.ForeignKey(
        ReturnReason, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_reason'
    )
    return_description = models.TextField(blank=True, null=True)
    return_photo = models.ImageField(upload_to='returns/', max_length=500, blank=True, null=True)
    return_status = models.CharField(max_length=30, default='NEW')
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refund_commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    return_decision = models.TextField(blank=True, null=True)
    is_locked = models.BooleanField(default=False)
    version = models.IntegerField(default=1)
    decided_by = models.ForeignKey(
        AuthCredentials,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='decided_by',
        related_name='returns_decided',
    )
    decided_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'returns'
        verbose_name = 'Возврат'
        verbose_name_plural = 'Возвраты'

    def __str__(self):
        return f'Возврат #{self.id_return} по заказу {self.id_order}'


class Review(models.Model):
    """Отзыв или вопрос о товаре (таблица reviews)."""

    id_review = models.BigAutoField(primary_key=True)
    id_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        db_column='id_product',
        related_name='reviews',
    )
    id_user = models.ForeignKey(
        AuthCredentials,
        on_delete=models.CASCADE,
        db_column='id_user',
        related_name='reviews',
    )
    id_order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='id_order',
        related_name='reviews',
    )
    review_type = models.CharField(max_length=20, default='review')
    review_rating = models.SmallIntegerField(
        blank=True, null=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    review_text = models.TextField(blank=True, null=True)
    review_photo = models.ImageField(upload_to='reviews/', max_length=500, blank=True, null=True)
    review_status = models.CharField(max_length=20, default='pending')
    seller_answer = models.TextField(blank=True, null=True)
    answered_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviews'
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'

    def __str__(self):
        return f'Отзыв #{self.id_review} — {self.id_product}'


class AuditLog(models.Model):
    """Журнал аудита (таблица audit_log)."""

    id_audit = models.BigAutoField(primary_key=True)
    id_user = models.ForeignKey(
        AuthCredentials,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        db_column='id_user',
        related_name='audit_entries',
    )
    audit_object_type = models.CharField(max_length=50)
    object_id = models.BigIntegerField(blank=True, null=True)
    audit_action = models.CharField(max_length=50)
    audit_reason = models.CharField(max_length=500, blank=True, null=True)
    audit_before = models.TextField(blank=True, null=True)
    audit_after = models.TextField(blank=True, null=True)
    audit_ip = models.GenericIPAddressField(blank=True, null=True)
    audit_user_agent = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'
        indexes = [
            models.Index(fields=['audit_object_type', 'object_id'], name='audit_object_idx'),
            models.Index(fields=['-created_at'], name='audit_created_idx'),
        ]
        verbose_name = 'Запись аудита'
        verbose_name_plural = 'Журнал аудита'

    def __str__(self):
        return f'{self.audit_action} {self.audit_object_type} #{self.object_id}'


class OrderItem(models.Model):
    """Позиция заказа (таблица order_items)."""

    id_order_item = models.BigAutoField(primary_key=True)
    id_order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        db_column='id_order',
        related_name='items',
    )
    id_product = models.ForeignKey(
        Product,
        on_delete=models.RESTRICT,
        db_column='id_product',
        related_name='order_items',
    )
    order_item_quantity = models.IntegerField()
    order_item_price = models.DecimalField(max_digits=12, decimal_places=2)
    order_item_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    order_item_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = 'order_items'
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Позиции заказов'

    def __str__(self):
        return f'{self.id_order} — {self.id_product} x{self.order_item_quantity}'


class CartItem(models.Model):
    """Позиция корзины (таблица cart_items)."""

    id_cart_item = models.BigAutoField(primary_key=True)
    id_cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        db_column='id_cart',
        related_name='items',
    )
    id_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        db_column='id_product',
        related_name='cart_items',
    )
    cart_item_quantity = models.IntegerField()
    cart_item_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = 'cart_items'
        verbose_name = 'Позиция корзины'
        verbose_name_plural = 'Позиции корзин'

    def __str__(self):
        return f'Корзина {self.id_cart} — {self.id_product} x{self.cart_item_quantity}'


class PromotionProduct(models.Model):
    """Связь акции с товаром (таблица promotion_products)."""

    id_promotion_product = models.BigAutoField(primary_key=True)
    id_promotion = models.ForeignKey(
        Promotion,
        on_delete=models.CASCADE,
        db_column='id_promotion',
        related_name='promotion_products',
    )
    id_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        db_column='id_product',
        related_name='promotion_links',
    )

    class Meta:
        db_table = 'promotion_products'
        verbose_name = 'Товар в акции'
        verbose_name_plural = 'Товары в акциях'

    def __str__(self):
        return f'{self.id_promotion} → {self.id_product}'


class PromotionCategory(models.Model):
    """Связь акции с категорией (таблица promotion_categories)."""

    id_promotion_category = models.BigAutoField(primary_key=True)
    id_promotion = models.ForeignKey(
        Promotion,
        on_delete=models.CASCADE,
        db_column='id_promotion',
        related_name='promotion_categories',
    )
    id_category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        db_column='id_category',
        related_name='promotion_links',
    )

    class Meta:
        db_table = 'promotion_categories'
        verbose_name = 'Категория в акции'
        verbose_name_plural = 'Категории в акциях'

    def __str__(self):
        return f'{self.id_promotion} → {self.id_category}'


class PromotionBrand(models.Model):
    """Связь акции с брендом (таблица promotion_brands)."""

    id_promotion_brand = models.BigAutoField(primary_key=True)
    id_promotion = models.ForeignKey(
        Promotion,
        on_delete=models.CASCADE,
        db_column='id_promotion',
        related_name='promotion_brands',
    )
    id_brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        db_column='id_brand',
        related_name='promotion_links',
    )

    class Meta:
        db_table = 'promotion_brands'
        verbose_name = 'Бренд в акции'
        verbose_name_plural = 'Бренды в акциях'

    def __str__(self):
        return f'{self.id_promotion} → {self.id_brand}'


class OrderPromotion(models.Model):
    """Применённая акция в заказе (таблица order_promotions)."""

    id_order_promotion = models.BigAutoField(primary_key=True)
    id_order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        db_column='id_order',
        related_name='order_promotions',
    )
    id_promotion = models.ForeignKey(
        Promotion,
        on_delete=models.CASCADE,
        db_column='id_promotion',
        related_name='order_promotions',
    )
    order_promotion_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'order_promotions'
        verbose_name = 'Акция в заказе'
        verbose_name_plural = 'Акции в заказах'

    def __str__(self):
        return f'{self.id_order} — скидка {self.order_promotion_discount}'


class ReturnItem(models.Model):
    """Позиция возврата (таблица return_items)."""

    id_return_item = models.BigAutoField(primary_key=True)
    id_return = models.ForeignKey(
        Return,
        on_delete=models.CASCADE,
        db_column='id_return',
        related_name='items',
    )
    id_order_item = models.ForeignKey(
        OrderItem,
        on_delete=models.RESTRICT,
        db_column='id_order_item',
        related_name='return_items',
    )
    return_item_quantity = models.IntegerField(validators=[MinValueValidator(1)])
    return_item_refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_defect = models.BooleanField(default=False)

    class Meta:
        db_table = 'return_items'
        verbose_name = 'Позиция возврата'
        verbose_name_plural = 'Позиции возвратов'

    def __str__(self):
        return f'Возврат {self.id_return} — позиция {self.id_order_item}'


class StockMovement(models.Model):
    """Движения склада: приход, списание, резерв, возврат (таблица stock_movements)."""

    TYPES = [
        ('receipt', 'Приход'),
        ('write_off', 'Списание'),
        ('adjustment', 'Корректировка'),
        ('reserve', 'Резерв'),
        ('release', 'Снятие резерва'),
        ('return', 'Возврат на склад'),
        ('defect', 'Списание в брак'),
        ('cancel_restore', 'Возврат при отмене'),
        ('import', 'Импорт остатков'),
    ]

    id_movement = models.BigAutoField(primary_key=True)
    id_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, db_column='id_product', related_name='movements'
    )
    movement_type = models.CharField(max_length=20, choices=TYPES)
    movement_quantity = models.IntegerField()
    expected_quantity = models.IntegerField(blank=True, null=True)
    quantity_after = models.IntegerField()
    reserved_after = models.IntegerField()
    movement_reason = models.CharField(max_length=500, blank=True, null=True)
    document_number = models.CharField(max_length=50, blank=True, null=True)
    id_order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_order',
        related_name='stock_movements',
    )
    id_user = models.ForeignKey(
        AuthCredentials, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_user'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'stock_movements'
        indexes = [
            models.Index(fields=['id_product', '-created_at'], name='movements_product_idx'),
            models.Index(fields=['movement_type', '-created_at'], name='movements_type_idx'),
        ]
        verbose_name = 'Движение склада'
        verbose_name_plural = 'Движения склада'


class Reservation(models.Model):
    """Резерв товара под корзину или заказ (таблица reservations)."""

    id_reservation = models.BigAutoField(primary_key=True)
    id_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, db_column='id_product', related_name='reservations'
    )
    id_cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, blank=True, null=True, db_column='id_cart',
        related_name='reservations',
    )
    id_order = models.ForeignKey(
        Order, on_delete=models.CASCADE, blank=True, null=True, db_column='id_order',
        related_name='reservations',
    )
    reservation_quantity = models.IntegerField(validators=[MinValueValidator(1)])
    reservation_status = models.CharField(max_length=20, default='active')
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reservations'
        indexes = [models.Index(fields=['reservation_status', 'expires_at'], name='reservations_expiry_idx')]
        verbose_name = 'Резерв'
        verbose_name_plural = 'Резервы'


class PaymentLog(models.Model):
    """Лог запросов/ответов платёжного шлюза (таблица payment_logs)."""

    id_payment_log = models.BigAutoField(primary_key=True)
    id_payment = models.ForeignKey(
        Payment, on_delete=models.CASCADE, db_column='id_payment', related_name='logs'
    )
    log_direction = models.CharField(max_length=20)
    log_payload = models.JSONField(blank=True, null=True)
    http_status = models.SmallIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payment_logs'
        verbose_name = 'Лог платежа'
        verbose_name_plural = 'Логи платежей'


class BankStatementImport(models.Model):
    """Загрузка выписки банка/эквайринга (таблица bank_statement_imports)."""

    id_import = models.BigAutoField(primary_key=True)
    file_name = models.CharField(max_length=255)
    statement_source = models.CharField(max_length=20, default='bank')
    rows_total = models.IntegerField(default=0)
    rows_matched = models.IntegerField(default=0)
    rows_mismatched = models.IntegerField(default=0)
    id_user = models.ForeignKey(
        AuthCredentials, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_user'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bank_statement_imports'
        verbose_name = 'Импорт выписки'
        verbose_name_plural = 'Импорты выписок'


class BankStatementLine(models.Model):
    """Строка выписки и результат сверки (таблица bank_statement_lines)."""

    id_line = models.BigAutoField(primary_key=True)
    id_import = models.ForeignKey(
        BankStatementImport, on_delete=models.CASCADE, db_column='id_import', related_name='lines'
    )
    row_number = models.IntegerField()
    order_number = models.CharField(max_length=50, blank=True, null=True)
    line_amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    operation_date = models.DateField(blank=True, null=True)
    match_status = models.CharField(max_length=20)
    match_note = models.CharField(max_length=500, blank=True, null=True)
    id_order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_order'
    )
    id_payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_payment'
    )
    raw_data = models.JSONField(blank=True, null=True)

    class Meta:
        db_table = 'bank_statement_lines'
        verbose_name = 'Строка выписки'
        verbose_name_plural = 'Строки выписок'


class Wishlist(models.Model):
    """Избранное покупателя (таблица wishlist)."""

    id_wishlist = models.BigAutoField(primary_key=True)
    id_user = models.ForeignKey(
        AuthCredentials, on_delete=models.CASCADE, db_column='id_user', related_name='wishlist'
    )
    id_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, db_column='id_product', related_name='wishlisted'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wishlist'
        constraints = [
            models.UniqueConstraint(fields=['id_user', 'id_product'], name='wishlist_unique'),
        ]
        verbose_name = 'Избранное'
        verbose_name_plural = 'Избранное'


class ImportJob(models.Model):
    """Журнал импортов CSV (таблица import_jobs)."""

    id_import_job = models.BigAutoField(primary_key=True)
    import_kind = models.CharField(max_length=20)
    file_name = models.CharField(max_length=255)
    import_status = models.CharField(max_length=20)
    rows_total = models.IntegerField(default=0)
    rows_ok = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)
    import_errors = models.JSONField(blank=True, null=True)
    duration_ms = models.IntegerField(default=0)
    id_user = models.ForeignKey(
        AuthCredentials, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_user'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'import_jobs'
        verbose_name = 'Импорт'
        verbose_name_plural = 'Импорты'


class BackupRecord(models.Model):
    """Резервные копии БД и результаты проверки restore (таблица backups)."""

    id_backup = models.BigAutoField(primary_key=True)
    backup_kind = models.CharField(max_length=20)
    file_path = models.CharField(max_length=500)
    file_size = models.BigIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True, null=True)
    backup_status = models.CharField(max_length=20)
    backup_output = models.TextField(blank=True, null=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    verify_status = models.CharField(max_length=20, blank=True, null=True)
    restored_at = models.DateTimeField(blank=True, null=True)
    id_user = models.ForeignKey(
        AuthCredentials, on_delete=models.SET_NULL, blank=True, null=True, db_column='id_user'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'backups'
        verbose_name = 'Резервная копия'
        verbose_name_plural = 'Резервные копии'


class ScheduledJob(models.Model):
    """Регламентные задания СУБД (таблица db_jobs)."""

    id_job = models.BigAutoField(primary_key=True)
    job_code = models.SlugField(max_length=50, unique=True)
    job_name = models.CharField(max_length=255)
    job_schedule = models.CharField(max_length=100)
    job_command = models.CharField(max_length=255)
    is_enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(blank=True, null=True)
    last_status = models.CharField(max_length=20, blank=True, null=True)
    last_output = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'db_jobs'
        verbose_name = 'Регламентное задание'
        verbose_name_plural = 'Регламентные задания'


class ArchivedOrder(models.Model):
    """Архив устаревших заказов (таблица orders_archive)."""

    id_archive = models.BigAutoField(primary_key=True)
    original_order_id = models.BigIntegerField(unique=True)
    order_number = models.CharField(max_length=50, db_index=True)
    customer_email = models.CharField(max_length=255)
    order_total = models.DecimalField(max_digits=12, decimal_places=2)
    order_created_at = models.DateTimeField()
    archive_payload = models.JSONField()
    archived_by = models.ForeignKey(
        AuthCredentials, on_delete=models.SET_NULL, blank=True, null=True, db_column='archived_by'
    )
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'orders_archive'
        verbose_name = 'Архивный заказ'
        verbose_name_plural = 'Архив заказов'


class ArchiveAccessGrant(models.Model):
    """Временный доступ к архивным данным (таблица archive_access_grants)."""

    id_grant = models.BigAutoField(primary_key=True)
    id_user = models.ForeignKey(
        AuthCredentials, on_delete=models.CASCADE, db_column='id_user', related_name='archive_grants'
    )
    granted_by = models.ForeignKey(
        AuthCredentials, on_delete=models.SET_NULL, blank=True, null=True, db_column='granted_by',
        related_name='archive_grants_given',
    )
    grant_reason = models.CharField(max_length=500)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'archive_access_grants'
        verbose_name = 'Доступ к архиву'
        verbose_name_plural = 'Доступы к архиву'