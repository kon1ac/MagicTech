from django.db import models

from users.models import AuthCredentials


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
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'

    def __str__(self):
        return f'{self.product_sku} — {self.product_name}'


class Price(models.Model):
    """Цена товара (таблица prices)."""

    id_price = models.BigAutoField(primary_key=True)
    id_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        db_column='id_product',
        related_name='prices',
    )
    product_price = models.DecimalField(max_digits=12, decimal_places=2)
    price_currency = models.CharField(max_length=3, default='RUB')
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
    promotion_promo_code = models.CharField(max_length=50, blank=True, null=True)
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
    total_items = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    order_payment_method = models.CharField(max_length=30, blank=True, null=True)
    order_payment_status = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'orders'
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
    payment_provider = models.CharField(max_length=30)
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
    return_status = models.CharField(max_length=30, default='NEW')
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
    review_rating = models.SmallIntegerField(blank=True, null=True)
    review_text = models.TextField(blank=True, null=True)
    review_status = models.CharField(max_length=20, default='pending')
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
    audit_before = models.TextField(blank=True, null=True)
    audit_after = models.TextField(blank=True, null=True)
    audit_ip = models.GenericIPAddressField(blank=True, null=True)
    audit_user_agent = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'
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
    return_item_quantity = models.IntegerField()
    return_item_refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = 'return_items'
        verbose_name = 'Позиция возврата'
        verbose_name_plural = 'Позиции возвратов'

    def __str__(self):
        return f'Возврат {self.id_return} — позиция {self.id_order_item}'
