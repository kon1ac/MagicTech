from django.urls import path

from panel import views

app_name = 'panel'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.dashboard_view, name='dashboard'),
    path('help/hotkeys/', views.hotkeys_help_view, name='hotkeys'),
    path('users/', views.user_list_view, name='user_list'),
    path('users/new/', views.user_create_view, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit_view, name='user_edit'),
    path('categories/', views.category_list_view, name='category_list'),
    path('categories/new/', views.category_create_view, name='category_create'),
    path('brands/', views.brand_list_view, name='brand_list'),
    path('brands/new/', views.brand_create_view, name='brand_create'),
    path('products/', views.product_list_view, name='product_list'),
    path('products/new/', views.product_create_view, name='product_create'),
    path('promotions/', views.promotion_list_view, name='promotion_list'),
    path('promotions/new/', views.promotion_create_view, name='promotion_create'),
    path('orders/', views.order_list_view, name='order_list'),
    path('orders/<int:pk>/', views.order_detail_view, name='order_detail'),
    path('orders/<int:pk>/pick/', views.order_pick_view, name='order_pick'),
    path('stock/', views.stock_list_view, name='stock_list'),
    path('stock/<int:product_id>/adjust/', views.stock_adjust_view, name='stock_adjust'),
    path('payments/', views.payment_list_view, name='payment_list'),
    path('returns/', views.return_list_view, name='return_list'),
    path('reviews/', views.review_list_view, name='review_list'),
    path('reviews/<int:pk>/moderate/', views.review_moderate_view, name='review_moderate'),
    path('audit/', views.audit_list_view, name='audit_list'),
    path('audit/export.csv', views.audit_export_view, name='audit_export'),
    path('system/', views.system_info_view, name='system_info'),
]
