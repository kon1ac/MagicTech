from rest_framework import serializers

from shop.models import Category, Order, OrderItem, Product, Review


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id_category', 'category_name', 'category_slug', 'category_level', 'id_parent']


class ProductSerializer(serializers.ModelSerializer):
    brand = serializers.CharField(source='id_brand.brand_name', default=None, read_only=True)
    category = serializers.CharField(source='id_category.category_name', default=None, read_only=True)
    price = serializers.DecimalField(source='price_now', max_digits=12, decimal_places=2, read_only=True, allow_null=True)
    available = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = ['product_sku', 'product_ean', 'product_name', 'brand', 'category', 'price', 'available',
                  'rating_avg', 'rating_count', 'product_characteristics']


class ProductDetailSerializer(ProductSerializer):
    images = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + ['product_description', 'images', 'seo_title', 'seo_description']

    def get_images(self, obj) -> list[str]:
        return [m.url for m in obj.media.all() if m.url]


class StockSerializer(serializers.Serializer):
    sku = serializers.CharField()
    quantity = serializers.IntegerField()
    reserved = serializers.IntegerField()
    available = serializers.IntegerField()


class PriceSerializer(serializers.Serializer):
    sku = serializers.CharField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    valid_from = serializers.DateTimeField()


class OrderItemSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source='id_product.product_sku')
    name = serializers.CharField(source='id_product.product_name')

    class Meta:
        model = OrderItem
        fields = ['sku', 'name', 'order_item_quantity', 'order_item_price', 'order_item_discount', 'order_item_total']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer = serializers.EmailField(source='id_user.email', read_only=True)

    class Meta:
        model = Order
        fields = ['order_number', 'order_status', 'order_payment_method', 'order_payment_status', 'order_channel',
                  'external_order_id', 'customer', 'subtotal', 'discount_total', 'total', 'delivery_address',
                  'created_at', 'paid_at', 'shipped_at', 'tracking_number', 'items']


class CartItemInSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=0, max_value=999)


class CartSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField())
    promo_code = serializers.CharField(allow_null=True)
    promo_error = serializers.CharField(allow_null=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    discount = serializers.DecimalField(max_digits=12, decimal_places=2)
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    reserved_until = serializers.DateTimeField(allow_null=True)


class CheckoutSerializer(serializers.Serializer):
    payment_method = serializers.ChoiceField(choices=['card_online', 'cash_on_delivery'])
    delivery_address = serializers.CharField(max_length=500)
    contact_phone = serializers.CharField(max_length=30)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    offer_accepted = serializers.BooleanField()
    promo_code = serializers.CharField(max_length=50, required=False, allow_blank=True)


class MarketplaceOrderItemSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=100)
    quantity = serializers.IntegerField(min_value=1, max_value=999)


class MarketplaceOrderSerializer(serializers.Serializer):
    external_order_id = serializers.CharField(max_length=100)
    marketplace = serializers.CharField(max_length=30)
    customer_email = serializers.EmailField()
    delivery_address = serializers.CharField(max_length=500)
    contact_phone = serializers.CharField(max_length=30)
    items = MarketplaceOrderItemSerializer(many=True)


class ShipmentSerializer(serializers.Serializer):
    tracking_number = serializers.CharField(max_length=100, required=False, allow_blank=True)


class ReviewInSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    text = serializers.CharField(max_length=5000)
    is_question = serializers.BooleanField(default=False)


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['id_review', 'review_type', 'review_rating', 'review_text', 'seller_answer', 'review_status', 'created_at', 'author']

    def get_author(self, obj) -> str:
        profile = getattr(obj.id_user, 'profile', None)
        return (profile.profile_first_name if profile and profile.profile_first_name else 'Покупатель')


class StatusChangeSerializer(serializers.Serializer):
    status = serializers.CharField(max_length=20)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class StockOperationSerializer(serializers.Serializer):
    quantity = serializers.IntegerField()
    reason = serializers.CharField(max_length=500)
    document_number = serializers.CharField(max_length=50, required=False, allow_blank=True)


class TokenRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()


class TokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    expires_at = serializers.DateTimeField()


class ErrorSerializer(serializers.Serializer):
    error = serializers.DictField()
