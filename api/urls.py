from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from api import views as v

app_name = 'api'

urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='api:schema'), name='docs'),
    # маркетплейсы
    path('v1/marketplace/products/', v.MarketplaceProductsView.as_view()),
    path('v1/marketplace/stock/', v.MarketplaceStockView.as_view()),
    path('v1/marketplace/prices/', v.MarketplacePricesView.as_view()),
    path('v1/marketplace/orders/', v.MarketplaceOrdersView.as_view()),
    path('v1/marketplace/orders/<str:number>/ship/', v.MarketplaceShipView.as_view()),
    # мобильное приложение
    path('v1/mobile/auth/token/', v.MobileTokenView.as_view()),
    path('v1/mobile/catalog/categories/', v.MobileCategoriesView.as_view()),
    path('v1/mobile/catalog/products/', v.MobileProductsView.as_view()),
    path('v1/mobile/catalog/products/<str:sku>/', v.MobileProductDetailView.as_view()),
    path('v1/mobile/catalog/products/<str:sku>/reviews/', v.MobileReviewsView.as_view()),
    path('v1/mobile/cart/', v.MobileCartView.as_view()),
    path('v1/mobile/cart/items/', v.MobileCartItemsView.as_view()),
    path('v1/mobile/orders/', v.MobileOrdersView.as_view()),
    path('v1/mobile/orders/<str:number>/', v.MobileOrderDetailView.as_view()),
    # платёжный шлюз
    path('v1/payments/yookassa/webhook/', v.YooKassaWebhookView.as_view()),
    # внутренние
    path('v1/internal/orders/', v.InternalOrdersView.as_view()),
    path('v1/internal/orders/<str:number>/status/', v.InternalOrderStatusView.as_view()),
    path('v1/internal/stock/<str:sku>/receipt/', v.InternalStockReceiptView.as_view()),
    path('v1/internal/stock/<str:sku>/adjust/', v.InternalStockAdjustView.as_view()),
]
