from django.contrib import admin

from .models import (
    AuditLog,
    Brand,
    Cart,
    CartItem,
    Category,
    Order,
    OrderItem,
    OrderPromotion,
    Payment,
    Price,
    Product,
    Promotion,
    PromotionBrand,
    PromotionCategory,
    PromotionProduct,
    Return,
    ReturnItem,
    Review,
    Stock,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ('id_product',)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    raw_id_fields = ('id_product',)


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    raw_id_fields = ('id_order_item',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id_category', 'category_name', 'category_slug', 'category_level', 'is_active')
    list_filter = ('category_level', 'is_active')
    search_fields = ('category_name', 'category_slug')
    raw_id_fields = ('id_parent',)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('id_brand', 'brand_name', 'brand_slug', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('brand_name', 'brand_slug')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'id_product',
        'product_sku',
        'product_name',
        'id_brand',
        'id_category',
        'is_active',
        'created_at',
    )
    list_filter = ('is_active', 'id_brand', 'id_category', 'created_at')
    search_fields = ('product_sku', 'product_ean', 'product_name')
    raw_id_fields = ('id_brand', 'id_category')


@admin.register(Price)
class PriceAdmin(admin.ModelAdmin):
    list_display = (
        'id_price',
        'id_product',
        'product_price',
        'price_currency',
        'valid_from',
        'valid_to',
        'id_user',
    )
    list_filter = ('price_currency', 'valid_from')
    search_fields = ('id_product__product_sku', 'id_product__product_name')
    raw_id_fields = ('id_product', 'id_user')


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = (
        'id_promotion',
        'promotion_name',
        'promotion_type',
        'promotion_value',
        'promotion_promo_code',
        'is_active',
        'start_at',
        'end_at',
    )
    list_filter = ('promotion_type', 'is_active', 'start_at', 'end_at')
    search_fields = ('promotion_name', 'promotion_promo_code')
    raw_id_fields = ('id_user',)


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        'id_stock',
        'id_product',
        'stock_quantity',
        'stock_reserved',
        'stock_movement_type',
        'updated_at',
    )
    list_filter = ('stock_movement_type',)
    search_fields = ('id_product__product_sku', 'id_product__product_name')
    raw_id_fields = ('id_product',)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id_cart', 'id_user', 'cart_session_id', 'cart_status', 'created_at', 'updated_at')
    list_filter = ('cart_status', 'created_at')
    search_fields = ('cart_session_id', 'id_user__email')
    raw_id_fields = ('id_user',)
    inlines = (CartItemInline,)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id_order',
        'order_number',
        'id_user',
        'order_status',
        'total',
        'discount_total',
        'order_payment_status',
        'created_at',
    )
    list_filter = ('order_status', 'order_payment_status', 'order_payment_method', 'created_at')
    search_fields = ('order_number', 'id_user__email')
    raw_id_fields = ('id_user',)
    inlines = (OrderItemInline,)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id_payment',
        'id_order',
        'payment_provider',
        'payment_amount',
        'payment_currency',
        'payment_status',
        'created_at',
    )
    list_filter = ('payment_provider', 'payment_status', 'payment_currency', 'created_at')
    search_fields = ('id_order__order_number',)
    raw_id_fields = ('id_order', 'id_user')


@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ('id_return', 'id_order', 'id_user', 'return_status', 'return_reason', 'created_at')
    list_filter = ('return_status', 'created_at')
    search_fields = ('id_order__order_number', 'id_user__email', 'return_reason')
    raw_id_fields = ('id_order', 'id_user')
    inlines = (ReturnItemInline,)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        'id_review',
        'id_product',
        'id_user',
        'review_type',
        'review_rating',
        'review_status',
        'created_at',
    )
    list_filter = ('review_type', 'review_status', 'review_rating', 'created_at')
    search_fields = ('review_text', 'id_product__product_name', 'id_user__email')
    raw_id_fields = ('id_product', 'id_user', 'id_order')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id_audit', 'id_user', 'audit_object_type', 'object_id', 'audit_action', 'created_at')
    list_filter = ('audit_object_type', 'audit_action', 'created_at')
    search_fields = ('audit_object_type', 'audit_action', 'id_user__email')
    raw_id_fields = ('id_user',)
    readonly_fields = (
        'created_at',
        'audit_before',
        'audit_after',
        'audit_ip',
        'audit_user_agent',
    )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'id_order_item',
        'id_order',
        'id_product',
        'order_item_quantity',
        'order_item_price',
        'order_item_total',
    )
    search_fields = ('id_order__order_number', 'id_product__product_sku')
    raw_id_fields = ('id_order', 'id_product')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = (
        'id_cart_item',
        'id_cart',
        'id_product',
        'cart_item_quantity',
        'cart_item_price_snapshot',
    )
    search_fields = ('id_cart__id_cart', 'id_product__product_sku')
    raw_id_fields = ('id_cart', 'id_product')


@admin.register(PromotionProduct)
class PromotionProductAdmin(admin.ModelAdmin):
    list_display = ('id_promotion_product', 'id_promotion', 'id_product')
    raw_id_fields = ('id_promotion', 'id_product')


@admin.register(PromotionCategory)
class PromotionCategoryAdmin(admin.ModelAdmin):
    list_display = ('id_promotion_category', 'id_promotion', 'id_category')
    raw_id_fields = ('id_promotion', 'id_category')


@admin.register(PromotionBrand)
class PromotionBrandAdmin(admin.ModelAdmin):
    list_display = ('id_promotion_brand', 'id_promotion', 'id_brand')
    raw_id_fields = ('id_promotion', 'id_brand')


@admin.register(OrderPromotion)
class OrderPromotionAdmin(admin.ModelAdmin):
    list_display = ('id_order_promotion', 'id_order', 'id_promotion', 'order_promotion_discount')
    raw_id_fields = ('id_order', 'id_promotion')


@admin.register(ReturnItem)
class ReturnItemAdmin(admin.ModelAdmin):
    list_display = (
        'id_return_item',
        'id_return',
        'id_order_item',
        'return_item_quantity',
        'return_item_refund_amount',
    )
    raw_id_fields = ('id_return', 'id_order_item')
<<<<<<< HEAD


# ---- реестры, добавленные во второй итерации: техническая регистрация для администратора
from .models import (  # noqa: E402
    ArchiveAccessGrant,
    ArchivedOrder,
    BackupRecord,
    BankStatementImport,
    BankStatementLine,
    Characteristic,
    ImportJob,
    OrderStatusRef,
    PaymentLog,
    ProductImage,
    PromotionTypeRef,
    Reservation,
    ReturnReason,
    ScheduledJob,
    StockMovement,
    Unit,
    Wishlist,
)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('id_movement', 'id_product', 'movement_type', 'movement_quantity', 'quantity_after', 'created_at')
    list_filter = ('movement_type',)
    raw_id_fields = ('id_product', 'id_order', 'id_user')


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('id_reservation', 'id_product', 'id_cart', 'id_order', 'reservation_quantity', 'reservation_status', 'expires_at')
    list_filter = ('reservation_status',)
    raw_id_fields = ('id_product', 'id_cart', 'id_order')


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display = ('id_payment_log', 'id_payment', 'log_direction', 'http_status', 'created_at')
    raw_id_fields = ('id_payment',)


for _model in (Unit, OrderStatusRef, ReturnReason, PromotionTypeRef, Characteristic, ProductImage, Wishlist,
               BankStatementImport, BankStatementLine, ImportJob, BackupRecord, ScheduledJob, ArchivedOrder,
               ArchiveAccessGrant):
    admin.site.register(_model)
=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
