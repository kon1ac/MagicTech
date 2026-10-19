from django.urls import path

from store import views

app_name = 'store'

urlpatterns = [
    path('', views.catalog_view, name='catalog'),
    path('catalog/<slug:slug>/', views.catalog_view, name='category'),
    path('product/<str:sku>/', views.product_view, name='product'),
    path('product/<str:sku>/review/', views.product_review_view, name='product_review'),
    path('product/<str:sku>/wishlist/', views.wishlist_toggle_view, name='wishlist_toggle'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/', views.cart_add_view, name='cart_add'),
    path('cart/update/', views.cart_update_view, name='cart_update'),
    path('cart/promo/', views.cart_promo_view, name='cart_promo'),
    path('checkout/', views.checkout_view, name='checkout'),
    path('pay/<uuid:uid>/', views.pay_view, name='pay'),
    path('offer/', views.offer_view, name='offer'),
    path('account/login/', views.login_view, name='login'),
    path('account/register/', views.register_view, name='register'),
    path('account/logout/', views.logout_view, name='logout'),
    path('account/', views.account_view, name='account'),
    path('account/orders/', views.account_orders_view, name='account_orders'),
    path('account/orders/<str:number>/', views.account_order_view, name='account_order'),
    path('account/orders/<str:number>/cancel/', views.account_order_cancel_view, name='account_order_cancel'),
    path('account/orders/<str:number>/return/', views.account_return_create_view, name='account_return_create'),
    path('account/returns/', views.account_returns_view, name='account_returns'),
    path('account/reviews/', views.account_reviews_view, name='account_reviews'),
    path('account/wishlist/', views.account_wishlist_view, name='account_wishlist'),
]
