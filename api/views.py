"""REST API: маркетплейсы, мобильное приложение, платёжный шлюз, внутренняя автоматизация."""

import secrets
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from api import serializers as s
from api.auth import HasScope, RoleAllowed
from shop.models import Cart, Category, Order, Price, Product, Review, Stock
from shop.services import cart as cart_service
from shop.services import catalog, orders as order_service, payments as payment_service
from shop.services import reviews as review_service
from shop.services.audit import write_audit
from shop.services.stock import adjust_stock, receive_stock
from users.auth_session import authenticate_credentials
from users.constants import ORDER_STATUS_LABELS, ROLE_CUSTOMER, STAFF_ROLES
from users.models import ApiToken, AuthCredentials, UserProfiles

ERRORS = {400: OpenApiResponse(s.ErrorSerializer, description='Ошибка валидации'),
          401: OpenApiResponse(s.ErrorSerializer, description='Нет или недействителен токен'),
          403: OpenApiResponse(s.ErrorSerializer, description='Недостаточно прав / нет scope'),
          404: OpenApiResponse(s.ErrorSerializer, description='Объект не найден')}


class Pagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class ScopedView(APIView):
    permission_classes = [IsAuthenticated, HasScope, RoleAllowed]
    required_scope = None
    rbac = None


class StaffOnly(RoleAllowed):
    def has_permission(self, request, view):
        return bool(request.user) and request.user.user_role in STAFF_ROLES


class CustomerOnly(RoleAllowed):
    def has_permission(self, request, view):
        return bool(request.user) and request.user.user_role == ROLE_CUSTOMER


# ================================================================ маркетплейсы

class MarketplaceView(ScopedView):
    required_scope = 'marketplace'
    permission_classes = [IsAuthenticated, HasScope, StaffOnly]


class MarketplaceProductsView(MarketplaceView):
    @extend_schema(tags=['Маркетплейсы'], summary='Выгрузка товаров (цены и остатки)',
                   parameters=[OpenApiParameter('updated_since', str, description='ISO-дата: только изменённые после'),
                               OpenApiParameter('page', int)],
                   responses={200: s.ProductSerializer(many=True), **ERRORS})
    def get(self, request):
        qs = catalog.base_queryset().order_by('pk')
        since = request.query_params.get('updated_since')
        if since:
            try:
                qs = qs.filter(updated_at__gte=timezone.datetime.fromisoformat(since))
            except ValueError as exc:
                raise ValidationError('updated_since: ожидается ISO-дата') from exc
        paginator = Pagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(s.ProductSerializer(page, many=True).data)


class MarketplaceStockView(MarketplaceView):
    @extend_schema(tags=['Маркетплейсы'], summary='Остатки (в реальном времени, без кеша)',
                   responses={200: s.StockSerializer(many=True), **ERRORS})
    def get(self, request):
        rows = Stock.objects.select_related('id_product').filter(id_product__is_active=True).order_by('id_product__product_sku')
        paginator = Pagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        data = [{'sku': r.id_product.product_sku, 'quantity': r.stock_quantity, 'reserved': r.stock_reserved,
                 'available': max(r.stock_quantity - r.stock_reserved, 0)} for r in page]
        return paginator.get_paginated_response(s.StockSerializer(data, many=True).data)


class MarketplacePricesView(MarketplaceView):
    @extend_schema(tags=['Маркетплейсы'], summary='Текущие цены', responses={200: s.PriceSerializer(many=True), **ERRORS})
    def get(self, request):
        rows = Price.objects.filter(valid_to__isnull=True, id_product__is_active=True).select_related('id_product').order_by('id_product__product_sku')
        paginator = Pagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        data = [{'sku': r.id_product.product_sku, 'price': r.product_price, 'currency': r.price_currency,
                 'valid_from': r.valid_from} for r in page]
        return paginator.get_paginated_response(s.PriceSerializer(data, many=True).data)


class MarketplaceOrdersView(MarketplaceView):
    @extend_schema(tags=['Маркетплейсы'], summary='Заказы с маркетплейсов',
                   parameters=[OpenApiParameter('status', str, enum=list(ORDER_STATUS_LABELS))],
                   responses={200: s.OrderSerializer(many=True), **ERRORS})
    def get(self, request):
        qs = Order.objects.filter(order_channel='marketplace').select_related('id_user').prefetch_related('items__id_product').order_by('-created_at')
        if request.query_params.get('status'):
            qs = qs.filter(order_status=request.query_params['status'])
        paginator = Pagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(s.OrderSerializer(page, many=True).data)

    @extend_schema(tags=['Маркетплейсы'], summary='Загрузка заказа с маркетплейса',
                   description='Атомарно: покупатель + заказ + резерв + платёж (оплачен на площадке). '
                               'Повтор с тем же external_order_id → 409.',
                   request=s.MarketplaceOrderSerializer, responses={201: s.OrderSerializer, 409: ERRORS[400], **ERRORS},
                   examples=[OpenApiExample('Заказ Ozon', value={
                       'external_order_id': 'OZ-100500', 'marketplace': 'ozon', 'customer_email': 'buyer@ozon.example',
                       'delivery_address': 'Москва, ПВЗ Ozon', 'contact_phone': '+79990000000',
                       'items': [{'sku': 'KB-LOG-001', 'quantity': 1}]})])
    def post(self, request):
        ser = s.MarketplaceOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if Order.objects.filter(order_channel='marketplace', external_order_id=data['external_order_id']).exists():
            return Response({'error': {'code': 'conflict', 'status': 409, 'message': 'Заказ уже загружен'}},
                            status=status.HTTP_409_CONFLICT)
        with transaction.atomic():
            customer, created = AuthCredentials.objects.get_or_create(
                email=data['customer_email'].lower(), defaults={'user_role': ROLE_CUSTOMER})
            if created:
                customer.set_password(secrets.token_urlsafe(16))
                customer.save()
                UserProfiles.objects.create(id_user=customer, profile_phone=data['contact_phone'])
            cart = Cart.objects.create(id_user=None, cart_session_id=f'mp-{data["external_order_id"]}'[:100])
            for item in data['items']:
                product = Product.objects.filter(product_sku=item['sku'], is_active=True).first()
                if not product:
                    raise ValidationError(f'Товар {item["sku"]} не найден')
                cart_service.add_item(cart, product, item['quantity'])
            order, _ = order_service.checkout(
                cart, user=customer, payment_method='marketplace', offer_accepted=True,
                delivery_address=data['delivery_address'], contact_phone=data['contact_phone'],
                comment=f'Маркетплейс {data["marketplace"]}', channel='marketplace',
                external_order_id=data['external_order_id'], request=request)
            payment_service.register_marketplace_payment(order, marketplace=data['marketplace'], actor=request.user,
                                                         request=request)
        order.refresh_from_db()
        return Response(s.OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class MarketplaceShipView(MarketplaceView):
    @extend_schema(tags=['Маркетплейсы'], summary='Подтверждение отгрузки', request=s.ShipmentSerializer,
                   responses={200: s.OrderSerializer, **ERRORS})
    def post(self, request, number):
        order = get_object_or_404(Order, order_number=number)
        ser = s.ShipmentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        order = order_service.confirm_shipment(order, actor=request.user,
                                               tracking_number=ser.validated_data.get('tracking_number', ''),
                                               request=request)
        return Response(s.OrderSerializer(order).data)


# ================================================================ мобильное приложение

class MobileTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle]

    @extend_schema(tags=['Мобильное приложение'], summary='Получить токен покупателя (30 дней)',
                   request=s.TokenRequestSerializer, responses={200: s.TokenResponseSerializer, 400: ERRORS[400]})
    def post(self, request):
        ser = s.TokenRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = authenticate_credentials(ser.validated_data['email'], ser.validated_data['password'], staff_only=False)
        if not user:
            raise ValidationError('Неверный email или пароль.')
        expires = timezone.now() + timedelta(days=30)
        token, key = ApiToken.issue(user, 'mobile-app', ['mobile'], expires_at=expires)
        write_audit(user=user, object_type='api_token', object_id=token.pk, action='issue_mobile', request=request)
        return Response({'token': key, 'expires_at': expires})


class MobileCategoriesView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=['Мобильное приложение'], summary='Категории', responses={200: s.CategorySerializer(many=True)})
    def get(self, request):
        return Response(s.CategorySerializer(Category.objects.filter(is_active=True).order_by('category_level', 'category_name'), many=True).data)


class MobileProductsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=['Мобильное приложение'], summary='Каталог с фильтрами (серверными)',
                   parameters=[OpenApiParameter('q', str), OpenApiParameter('category', str, description='slug'),
                               OpenApiParameter('brand', int, many=True), OpenApiParameter('price_min', float),
                               OpenApiParameter('price_max', float), OpenApiParameter('in_stock', int, enum=[0, 1]),
                               OpenApiParameter('sort', str, enum=list(catalog.SORTS)), OpenApiParameter('page', int)],
                   responses={200: s.ProductSerializer(many=True)})
    def get(self, request):
        qs, _, _ = catalog.search(catalog.parse_filters(request.query_params))
        paginator = Pagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(s.ProductSerializer(page, many=True).data)


class MobileProductDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=['Мобильное приложение'], summary='Карточка товара', responses={200: s.ProductDetailSerializer, 404: ERRORS[404]})
    def get(self, request, sku):
        product = catalog.base_queryset().prefetch_related('media').filter(product_sku=sku).first()
        if not product:
            raise NotFound('Товар не найден')
        return Response(s.ProductDetailSerializer(product).data)


class MobileReviewsView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAuthenticated(), HasScope(), CustomerOnly()]

    required_scope = 'mobile'

    @extend_schema(tags=['Мобильное приложение'], summary='Опубликованные отзывы и вопросы', responses={200: s.ReviewSerializer(many=True)})
    def get(self, request, sku):
        product = get_object_or_404(Product, product_sku=sku)
        qs = Review.objects.filter(id_product=product, review_status='approved').select_related('id_user__profile').order_by('-created_at')
        return Response(s.ReviewSerializer(qs[:100], many=True).data)

    @extend_schema(tags=['Мобильное приложение'], summary='Оставить отзыв (только купившим) или вопрос',
                   request=s.ReviewInSerializer, responses={201: s.ReviewSerializer, **ERRORS})
    def post(self, request, sku):
        product = get_object_or_404(Product, product_sku=sku, is_active=True)
        ser = s.ReviewInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        review = review_service.create_review(request.user, product, rating=ser.validated_data.get('rating'),
                                              text=ser.validated_data['text'], is_question=ser.validated_data['is_question'],
                                              request=request)
        return Response(s.ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class MobileView(ScopedView):
    required_scope = 'mobile'
    permission_classes = [IsAuthenticated, HasScope, CustomerOnly]


def _cart_payload(cart):
    totals = cart_service.totals(cart)
    return {
        'items': [{'sku': l.product.product_sku, 'name': l.product.product_name, 'quantity': l.quantity,
                   'price': str(l.price), 'discount': str(l.discount), 'total': str(l.total)} for l in totals.lines],
        'promo_code': cart.cart_promo_code, 'promo_error': totals.promo_error,
        'subtotal': str(totals.subtotal), 'discount': str(totals.discount), 'total': str(totals.total),
        'reserved_until': cart_service.reservation_expires_at(cart),
    }


class MobileCartView(MobileView):
    @extend_schema(tags=['Мобильное приложение'], summary='Текущая корзина с расчётом', responses={200: s.CartSerializer, **ERRORS})
    def get(self, request):
        return Response(_cart_payload(cart_service.get_cart(user=request.user)))

    @extend_schema(tags=['Мобильное приложение'], summary='Очистить корзину (резервы снимаются)', responses={204: None})
    def delete(self, request):
        cart_service.clear(cart_service.get_cart(user=request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)


class MobileCartItemsView(MobileView):
    @extend_schema(tags=['Мобильное приложение'], summary='Установить количество товара (0 — удалить)',
                   description='Серверная проверка остатка и резерв на 20 минут.',
                   request=s.CartItemInSerializer, responses={200: s.CartSerializer, **ERRORS})
    def post(self, request):
        ser = s.CartItemInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        product = Product.objects.filter(product_sku=ser.validated_data['sku'], is_active=True).first()
        if not product:
            raise NotFound('Товар не найден')
        cart = cart_service.get_cart(user=request.user)
        cart_service.set_quantity(cart, product, ser.validated_data['quantity'])
        return Response(_cart_payload(cart))


class MobileOrdersView(MobileView):
    @extend_schema(tags=['Мобильное приложение'], summary='История заказов', responses={200: s.OrderSerializer(many=True)})
    def get(self, request):
        qs = request.user.orders.prefetch_related('items__id_product').order_by('-created_at')
        paginator = Pagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(s.OrderSerializer(page, many=True).data)

    @extend_schema(tags=['Мобильное приложение'], summary='Оформить заказ из корзины (атомарно)',
                   request=s.CheckoutSerializer, responses={201: s.OrderSerializer, **ERRORS})
    def post(self, request):
        ser = s.CheckoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        cart = cart_service.get_cart(user=request.user)
        if data.get('promo_code') is not None:
            cart.cart_promo_code = data['promo_code'].strip().upper() or None
            cart.save(update_fields=['cart_promo_code'])
        order, payment = order_service.checkout(
            cart, user=request.user, payment_method=data['payment_method'], offer_accepted=data['offer_accepted'],
            delivery_address=data['delivery_address'], contact_phone=data['contact_phone'],
            comment=data.get('comment', ''), channel='mobile', request=request)
        body = s.OrderSerializer(order).data
        if payment:
            body['payment'] = {'payment_uid': str(payment.payment_uid), 'confirmation_url': f'/pay/{payment.payment_uid}/'}
        return Response(body, status=status.HTTP_201_CREATED)


class MobileOrderDetailView(MobileView):
    @extend_schema(tags=['Мобильное приложение'], summary='Заказ покупателя (только свой)', responses={200: s.OrderSerializer, 404: ERRORS[404]})
    def get(self, request, number):
        order = Order.objects.filter(order_number=number, id_user=request.user).prefetch_related('items__id_product').first()
        if not order:
            raise NotFound('Заказ не найден')  # чужой заказ неотличим от несуществующего
        return Response(s.OrderSerializer(order).data)


# ================================================================ платёжный шлюз

class YooKassaWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=['Платёжный шлюз'], summary='Callback ЮKassa (имитация)',
                   description='Тело — уведомление ЮKassa; заголовок X-Signature = HMAC-SHA256(тело, секрет). '
                               'Обработка идемпотентна; заказ + платёж + резерв меняются атомарно.',
                   request={'application/json': {'type': 'object'}},
                   responses={200: OpenApiResponse(description='{"status": "ok"}'), **ERRORS},
                   examples=[OpenApiExample('payment.succeeded', value={
                       'type': 'notification', 'event': 'payment.succeeded',
                       'object': {'id': 'yk-…', 'status': 'succeeded', 'amount': {'value': '4990.00', 'currency': 'RUB'}}})])
    def post(self, request):
        signature = request.headers.get('X-Signature')
        if not signature:
            raise ValidationError('Отсутствует заголовок X-Signature.')
        payment = payment_service.process_webhook(request.body, signature, request=request)
        return Response({'status': 'ok', 'payment_status': payment.payment_status})


# ================================================================ внутренняя автоматизация

class InternalView(ScopedView):
    required_scope = 'internal'


class InternalOrdersView(InternalView):
    rbac = ('orders', 'view')

    @extend_schema(tags=['Внутреннее API'], summary='Заказы', parameters=[OpenApiParameter('status', str)],
                   responses={200: s.OrderSerializer(many=True), **ERRORS})
    def get(self, request):
        qs = Order.objects.select_related('id_user').prefetch_related('items__id_product').order_by('-created_at')
        if request.query_params.get('status'):
            qs = qs.filter(order_status=request.query_params['status'])
        paginator = Pagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(s.OrderSerializer(page, many=True).data)


class InternalOrderStatusView(InternalView):
    rbac = ('orders', 'update_status')

    @extend_schema(tags=['Внутреннее API'], summary='Смена статуса заказа по регламенту',
                   request=s.StatusChangeSerializer, responses={200: s.OrderSerializer, **ERRORS})
    def post(self, request, number):
        order = get_object_or_404(Order, order_number=number)
        ser = s.StatusChangeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from users.permissions import has_permission

        if ser.validated_data['status'] == 'CANCELLED' and not has_permission(request.user.user_role, 'orders', 'cancel_critical'):
            raise PermissionDenied('Отмена — критическая операция администратора.')
        order = order_service.change_order_status(order, ser.validated_data['status'], actor=request.user,
                                                  reason=ser.validated_data.get('reason', ''), request=request)
        return Response(s.OrderSerializer(order).data)


class InternalStockReceiptView(InternalView):
    rbac = ('stock', 'receipt')

    @extend_schema(tags=['Внутреннее API'], summary='Приход товара', request=s.StockOperationSerializer,
                   responses={200: s.StockSerializer, **ERRORS})
    def post(self, request, sku):
        product = get_object_or_404(Product, product_sku=sku)
        ser = s.StockOperationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        receive_stock(product, ser.validated_data['quantity'], actor=request.user,
                      document_number=ser.validated_data.get('document_number', ''),
                      reason=ser.validated_data['reason'], request=request)
        stock = Stock.objects.get(id_product=product)
        return Response({'sku': sku, 'quantity': stock.stock_quantity, 'reserved': stock.stock_reserved,
                         'available': stock.available_quantity})


class InternalStockAdjustView(InternalView):
    rbac = ('stock', 'adjust_critical')

    @extend_schema(tags=['Внутреннее API'], summary='Критическая корректировка остатка (с причиной)',
                   request=s.StockOperationSerializer, responses={200: s.StockSerializer, **ERRORS})
    def post(self, request, sku):
        product = get_object_or_404(Product, product_sku=sku)
        ser = s.StockOperationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        stock = adjust_stock(product, ser.validated_data['quantity'], actor=request.user,
                             reason=ser.validated_data['reason'], request=request)
        return Response({'sku': sku, 'quantity': stock.stock_quantity, 'reserved': stock.stock_reserved,
                         'available': stock.available_quantity})
