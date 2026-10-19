<<<<<<< HEAD
"""Панель: вход, обзор, пользователи и роли, настройки пользователя, справка."""

from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, ProtectedError, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from panel.decorators import panel_login_required, permission_required
from panel.forms import LoginForm, UserForm, UserSettingsForm
from panel.listing import apply_sorting, default_filter_redirect, list_context, paginate
from shop.models import Order, Payment, Product, Review, Stock
from shop.services.audit import object_history, write_audit
from users.auth_session import authenticate_credentials, get_panel_user, login_user, logout_user
from users.constants import ORDER_STATUS_LABELS, ROLE_CHOICES, ROLE_LABELS
from users.models import AuthCredentials, SavedFilter, UserSettings
from users.permissions import ACTION_LABELS, PERMISSION_MATRIX
=======
import csv
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from panel.decorators import panel_login_required, permission_required
from panel.forms import (
    BrandForm,
    CategoryForm,
    LoginForm,
    OrderStatusForm,
    ProductForm,
    PromotionForm,
    ReviewModerationForm,
    StockAdjustForm,
    UserForm,
)
from shop.models import (
    AuditLog,
    Brand,
    Category,
    Order,
    Payment,
    Product,
    Promotion,
    Return,
    Review,
    Stock,
)
from shop.services.audit import write_audit
from shop.services.orders import change_order_status
from shop.services.stock import adjust_stock, write_off_for_order_item
from users.auth_session import authenticate_credentials, get_panel_user, login_user, logout_user
from users.constants import ORDER_STATUS_LABELS, ROLE_CUSTOMER
from users.models import AuthCredentials
from users.permissions import has_permission


def _paginate(request, queryset, per_page=25):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get('page'))
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if get_panel_user(request):
        return redirect('panel:dashboard')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate_credentials(form.cleaned_data['email'], form.cleaned_data['password'])
        if user:
            login_user(request, user)
<<<<<<< HEAD
            write_audit(user=user, object_type='session', object_id=user.id_user, action='login', request=request)
            next_url = request.GET.get('next', '')
            if next_url.startswith('/panel') and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
                return redirect(next_url)
            return redirect('panel:dashboard')
        write_audit(user=None, object_type='session', object_id=None, action='login_failed',
                    after={'email': form.cleaned_data['email']}, request=request)
=======
            write_audit(
                user=user,
                object_type='session',
                object_id=user.id_user,
                action='login',
                request=request,
            )
            return redirect('panel:dashboard')
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
        messages.error(request, 'Неверный email или пароль, либо нет доступа к панели.')
    return render(request, 'panel/login.html', {'form': form})


<<<<<<< HEAD
@require_POST
=======
@require_http_methods(['POST', 'GET'])
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
def logout_view(request):
    user = get_panel_user(request)
    if user:
        write_audit(user=user, object_type='session', object_id=user.id_user, action='logout', request=request)
    logout_user(request)
    return redirect('panel:login')


@panel_login_required
@permission_required('dashboard', 'view')
def dashboard_view(request):
    stats = {
        'products': Product.objects.filter(is_active=True).count(),
<<<<<<< HEAD
        'orders_open': Order.objects.exclude(order_status__in=['COMPLETED', 'CANCELLED', 'RETURNED']).count(),
        'revenue': Payment.objects.filter(payment_status__in=['SUCCESS', 'PARTIALLY_REFUNDED']).aggregate(
            s=Sum('payment_amount'))['s'] or Decimal('0'),
        'reviews_pending': Review.objects.filter(review_status='pending').count(),
        'assembly': Order.objects.filter(order_status='ASSEMBLY').count(),
        'low_stock': Stock.objects.filter(stock_quantity__lte=5).count(),
    }
    recent_orders = Order.objects.select_related('id_user').order_by('-created_at')[:8]
    status_breakdown = [
        {'code': row['order_status'], 'label': ORDER_STATUS_LABELS.get(row['order_status'], row['order_status']),
         'cnt': row['cnt']}
        for row in Order.objects.values('order_status').annotate(cnt=Count('id_order')).order_by('order_status')
    ]
    return render(request, 'panel/dashboard.html', {
        'stats': stats, 'recent_orders': recent_orders, 'status_breakdown': status_breakdown,
        'status_labels': ORDER_STATUS_LABELS,
    })


# ---------------------------------------------------------------- пользователи и роли

@panel_login_required
@permission_required('users', 'view')
def user_list_view(request):
    actor = request.panel_user
    if (resp := default_filter_redirect(request, actor, 'users')):
        return resp
    q = request.GET.get('q', '').strip()
    role = request.GET.get('role', '')
    active = request.GET.get('active', '')
    qs = AuthCredentials.objects.select_related('profile')
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(profile__profile_last_name__icontains=q)
                       | Q(profile__profile_phone__icontains=q))
    if role:
        qs = qs.filter(user_role=role)
    if active in ('1', '0'):
        qs = qs.filter(is_active=active == '1')
    qs, sort_keys = apply_sorting(request, qs, {
        'email': 'email', 'role': 'user_role', 'active': 'is_active', 'created': 'created_at'}, '-created')
    return render(request, 'panel/users/list.html', {
        'page_obj': paginate(request, qs, actor), 'q': q, 'role': role, 'active': active,
        'roles': ROLE_CHOICES, 'role_labels': ROLE_LABELS, **list_context(request, actor, 'users', sort_keys),
    })
=======
        'orders_open': Order.objects.exclude(order_status__in=['COMPLETED', 'CANCELLED']).count(),
        'revenue': Payment.objects.filter(payment_status='SUCCESS').aggregate(s=Sum('payment_amount'))['s']
        or Decimal('0'),
        'reviews_pending': Review.objects.filter(review_status='pending').count(),
    }
    recent_orders = Order.objects.select_related('id_user').order_by('-created_at')[:8]
    status_breakdown = [
        {
            'code': row['order_status'],
            'label': ORDER_STATUS_LABELS.get(row['order_status'], row['order_status']),
            'cnt': row['cnt'],
        }
        for row in Order.objects.values('order_status')
        .annotate(cnt=Count('id_order'))
        .order_by('order_status')
    ]
    return render(
        request,
        'panel/dashboard.html',
        {
            'stats': stats,
            'recent_orders': recent_orders,
            'status_breakdown': status_breakdown,
            'status_labels': ORDER_STATUS_LABELS,
        },
    )


@panel_login_required
@permission_required('users', 'view')
def user_list_view(request):
    q = request.GET.get('q', '').strip()
    qs = AuthCredentials.objects.exclude(user_role=ROLE_CUSTOMER).order_by('-created_at')
    if q:
        qs = qs.filter(email__icontains=q)
    role = request.GET.get('role')
    if role:
        qs = qs.filter(user_role=role)
    return render(request, 'panel/users/list.html', {'page_obj': _paginate(request, qs), 'q': q, 'role': role})
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719


@panel_login_required
@permission_required('users', 'create')
def user_create_view(request):
<<<<<<< HEAD
    form = UserForm(request.POST or None, actor=request.panel_user)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        write_audit(user=request.panel_user, object_type='user', object_id=user.id_user, action='create',
                    after={'email': user.email, 'role': user.user_role}, request=request)
        messages.success(request, 'Пользователь создан.')
        return redirect('panel:user_list')
    return render(request, 'panel/form.html', {'form': form, 'title': 'Новый пользователь',
                                               'back': 'panel:user_list'})
=======
    form = UserForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        write_audit(
            user=get_panel_user(request),
            object_type='user',
            object_id=user.id_user,
            action='create',
            after={'email': user.email, 'role': user.user_role},
            request=request,
        )
        messages.success(request, 'Пользователь создан.')
        return redirect('panel:user_list')
    return render(request, 'panel/users/form.html', {'form': form, 'title': 'Новый пользователь'})
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719


@panel_login_required
@permission_required('users', 'update')
def user_edit_view(request, pk):
    user = get_object_or_404(AuthCredentials, pk=pk)
<<<<<<< HEAD
    form = UserForm(request.POST or None, instance=user, actor=request.panel_user)
    if request.method == 'POST' and form.is_valid():
        before = {'email': user.email, 'role': user.user_role, 'is_active': user.is_active}
        user = form.save()
        after = {'email': user.email, 'role': user.user_role, 'is_active': user.is_active}
        write_audit(user=request.panel_user, object_type='user', object_id=user.id_user,
                    action='role_change' if before['role'] != after['role'] else 'update',
                    before=before, after=after, request=request)
        messages.success(request, 'Изменения сохранены.')
        return redirect('panel:user_list')
    return render(request, 'panel/form.html', {
        'form': form, 'title': f'Пользователь {user.email}', 'back': 'panel:user_list',
        'history': object_history('user', user.pk),
        'related': [('Заказы покупателя', f'/panel/orders/?q={user.email}')],
    })


@panel_login_required
@permission_required('users', 'delete')
@require_http_methods(['GET', 'POST'])
def user_delete_view(request, pk):
    user = get_object_or_404(AuthCredentials, pk=pk)
    if user.pk == request.panel_user.pk:
        messages.error(request, 'Нельзя удалить собственную учётную запись.')
        return redirect('panel:user_list')
    if request.method == 'POST' and request.POST.get('confirm'):
        snapshot = {'email': user.email, 'role': user.user_role}
        try:
            user.delete()
            action, text = 'delete', 'Пользователь удалён.'
        except ProtectedError:
            # есть заказы/возвраты — физически удалять нельзя, деактивируем
            user.is_active = False
            user.save(update_fields=['is_active', 'updated_at'])
            action, text = 'deactivate', 'У пользователя есть заказы — учётная запись деактивирована.'
        write_audit(user=request.panel_user, object_type='user', object_id=pk, action=action,
                    before=snapshot, request=request)
        messages.success(request, text)
        return redirect('panel:user_list')
    return render(request, 'panel/confirm.html', {
        'title': 'Удаление пользователя', 'object': user.email, 'back': 'panel:user_list',
        'text': 'Учётная запись будет удалена. Если у пользователя есть заказы — она будет деактивирована.'})


@panel_login_required
@permission_required('users', 'update')
@require_POST
def user_bulk_view(request):
    ids = [int(i) for i in request.POST.getlist('ids') if i.isdigit()]
    action = request.POST.get('action')
    if not request.POST.get('confirm'):
        messages.error(request, 'Подтвердите массовую операцию.')
        return redirect(request.META.get('HTTP_REFERER') or 'panel:user_list')
    ids = [i for i in ids if i != request.panel_user.pk]
    if action in ('activate', 'deactivate') and ids:
        AuthCredentials.objects.filter(pk__in=ids).update(is_active=action == 'activate')
        for pk in ids:
            write_audit(user=request.panel_user, object_type='user', object_id=pk, action=action,
                        reason='Массовая операция', request=request)
        messages.success(request, f'Обработано учётных записей: {len(ids)}.')
    return redirect(request.META.get('HTTP_REFERER') or 'panel:user_list')


@panel_login_required
@permission_required('users', 'view')
def rbac_matrix_view(request):
    resources = []
    for resource, actions in PERMISSION_MATRIX.items():
        for action, roles in actions.items():
            resources.append({'resource': resource, 'action': action, 'label': ACTION_LABELS.get(action, action),
                              'roles': [code in roles for code, _ in ROLE_CHOICES]})
    return render(request, 'panel/users/rbac.html', {'rows': resources, 'roles': ROLE_CHOICES})


# ---------------------------------------------------------------- настройки пользователя

@panel_login_required
def settings_view(request):
    actor = request.panel_user
    settings_obj = UserSettings.for_user(actor)
    form = UserSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Настройки сохранены на сервере.')
        return redirect('panel:settings')
    return render(request, 'panel/settings.html', {
        'form': form, 'saved_filters': SavedFilter.objects.filter(id_user=actor),
        'default_filters': settings_obj.default_filters or {},
    })


@panel_login_required
@require_POST
def settings_theme_view(request):
    theme = request.POST.get('theme')
    if theme not in ('light', 'dark'):
        return JsonResponse({'ok': False}, status=400)
    settings_obj = UserSettings.for_user(request.panel_user)
    settings_obj.theme = theme
    settings_obj.save(update_fields=['theme', 'updated_at'])
    return JsonResponse({'ok': True, 'theme': theme})


@panel_login_required
@require_POST
def saved_filter_create_view(request):
    section = request.POST.get('section', '')[:50]
    name = request.POST.get('name', '').strip()[:100]
    query = request.POST.get('query', '')[:1000]
    if section and name:
        SavedFilter.objects.create(id_user=request.panel_user, filter_section=section, filter_name=name,
                                   filter_query=query)
        if request.POST.get('as_default'):
            settings_obj = UserSettings.for_user(request.panel_user)
            defaults = dict(settings_obj.default_filters or {})
            defaults[section] = query
            settings_obj.default_filters = defaults
            settings_obj.save(update_fields=['default_filters', 'updated_at'])
        messages.success(request, 'Фильтр сохранён.')
    return redirect(request.META.get('HTTP_REFERER') or 'panel:dashboard')


@panel_login_required
@require_POST
def saved_filter_delete_view(request, pk):
    SavedFilter.objects.filter(pk=pk, id_user=request.panel_user).delete()
    return redirect(request.META.get('HTTP_REFERER') or 'panel:settings')


@panel_login_required
@require_POST
def default_filter_clear_view(request, section):
    settings_obj = UserSettings.for_user(request.panel_user)
    defaults = dict(settings_obj.default_filters or {})
    defaults.pop(section, None)
    settings_obj.default_filters = defaults
    settings_obj.save(update_fields=['default_filters', 'updated_at'])
    return redirect('panel:settings')
=======
    initial = {}
    if hasattr(user, 'profile'):
        initial = {
            'profile_first_name': user.profile.profile_first_name,
            'profile_last_name': user.profile.profile_last_name,
            'profile_phone': user.profile.profile_phone,
        }
    form = UserForm(request.POST or None, instance=user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        before = {'email': user.email, 'role': user.user_role, 'is_active': user.is_active}
        user = form.save()
        write_audit(
            user=get_panel_user(request),
            object_type='user',
            object_id=user.id_user,
            action='update',
            before=before,
            after={'email': user.email, 'role': user.user_role, 'is_active': user.is_active},
            request=request,
        )
        messages.success(request, 'Изменения сохранены.')
        return redirect('panel:user_list')
    return render(request, 'panel/users/form.html', {'form': form, 'title': 'Редактирование пользователя'})


def _catalog_list(request, model, template, search_fields, order='-pk'):
    q = request.GET.get('q', '').strip()
    qs = model.objects.all().order_by(order)
    if q:
        flt = Q()
        for field in search_fields:
            flt |= Q(**{f'{field}__icontains': q})
        qs = qs.filter(flt)
    return render(request, template, {'page_obj': _paginate(request, qs), 'q': q})


@panel_login_required
@permission_required('categories', 'view')
def category_list_view(request):
    return _catalog_list(request, Category, 'panel/catalog/category_list.html', ['category_name', 'category_slug'])


@panel_login_required
@permission_required('categories', 'create')
def category_create_view(request):
    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        write_audit(
            user=get_panel_user(request),
            object_type='category',
            object_id=obj.id_category,
            action='create',
            after={'name': obj.category_name},
            request=request,
        )
        messages.success(request, 'Категория сохранена.')
        return redirect('panel:category_list')
    return render(request, 'panel/catalog/category_form.html', {'form': form, 'title': 'Новая категория'})


@panel_login_required
@permission_required('brands', 'view')
def brand_list_view(request):
    return _catalog_list(request, Brand, 'panel/catalog/brand_list.html', ['brand_name', 'brand_slug'])


@panel_login_required
@permission_required('brands', 'create')
def brand_create_view(request):
    form = BrandForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        write_audit(
            user=get_panel_user(request),
            object_type='brand',
            object_id=obj.id_brand,
            action='create',
            after={'name': obj.brand_name},
            request=request,
        )
        messages.success(request, 'Бренд сохранён.')
        return redirect('panel:brand_list')
    return render(request, 'panel/catalog/brand_form.html', {'form': form, 'title': 'Новый бренд'})


@panel_login_required
@permission_required('products', 'view')
def product_list_view(request):
    return _catalog_list(
        request,
        Product,
        'panel/catalog/product_list.html',
        ['product_sku', 'product_name', 'product_ean'],
        order='-created_at',
    )


@panel_login_required
@permission_required('products', 'create')
def product_create_view(request):
    form = ProductForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        write_audit(
            user=get_panel_user(request),
            object_type='product',
            object_id=obj.id_product,
            action='create',
            after={'sku': obj.product_sku, 'name': obj.product_name},
            request=request,
        )
        messages.success(request, 'Товар создан.')
        return redirect('panel:product_list')
    return render(request, 'panel/catalog/product_form.html', {'form': form, 'title': 'Новый товар'})


@panel_login_required
@permission_required('promotions', 'view')
def promotion_list_view(request):
    return _catalog_list(
        request,
        Promotion,
        'panel/promotions/list.html',
        ['promotion_name', 'promotion_promo_code'],
        order='-start_at',
    )


@panel_login_required
@permission_required('promotions', 'create')
def promotion_create_view(request):
    form = PromotionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        promo = form.save(commit=False)
        promo.id_user = get_panel_user(request)
        promo.save()
        write_audit(
            user=get_panel_user(request),
            object_type='promotion',
            object_id=promo.id_promotion,
            action='create',
            after={'name': promo.promotion_name},
            request=request,
        )
        messages.success(request, 'Акция создана.')
        return redirect('panel:promotion_list')
    return render(request, 'panel/promotions/form.html', {'form': form, 'title': 'Новая акция'})


@panel_login_required
@permission_required('orders', 'view')
def order_list_view(request):
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    qs = Order.objects.select_related('id_user').order_by('-created_at')
    if q:
        qs = qs.filter(Q(order_number__icontains=q) | Q(id_user__email__icontains=q))
    if status:
        qs = qs.filter(order_status=status)
    return render(
        request,
        'panel/orders/list.html',
        {
            'page_obj': _paginate(request, qs),
            'q': q,
            'status': status,
            'status_labels': ORDER_STATUS_LABELS,
        },
    )


@panel_login_required
@permission_required('orders', 'view')
def order_detail_view(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('items__id_product'), pk=pk)
    actor = get_panel_user(request)
    can_change = has_permission(actor.user_role, 'orders', 'update_status')
    can_cancel = has_permission(actor.user_role, 'orders', 'cancel_critical')
    form = OrderStatusForm(request.POST or None, current_status=order.order_status)
    if request.method == 'POST' and can_change and form.is_valid():
        new_status = form.cleaned_data['new_status']
        if new_status == 'CANCELLED' and not can_cancel:
            messages.error(request, 'Отмена заказа доступна только администратору.')
        elif new_status == 'CANCELLED' and not form.cleaned_data.get('confirm_cancel'):
            messages.error(request, 'Подтвердите критическую операцию отмены.')
        else:
            try:
                change_order_status(
                    order,
                    new_status,
                    actor=actor,
                    reason=form.cleaned_data.get('reason') or '',
                    request=request,
                )
                messages.success(request, 'Статус заказа обновлён.')
                return redirect('panel:order_detail', pk=pk)
            except ValidationError as exc:
                messages.error(request, exc.messages[0] if exc.messages else str(exc))
    return render(
        request,
        'panel/orders/detail.html',
        {
            'order': order,
            'form': form,
            'status_labels': ORDER_STATUS_LABELS,
            'can_change': can_change,
        },
    )


@panel_login_required
@permission_required('stock', 'view')
def stock_list_view(request):
    q = request.GET.get('q', '').strip()
    qs = Stock.objects.select_related('id_product').order_by('-updated_at')
    if q:
        qs = qs.filter(
            Q(id_product__product_sku__icontains=q) | Q(id_product__product_name__icontains=q)
        )
    return render(request, 'panel/warehouse/stock_list.html', {'page_obj': _paginate(request, qs), 'q': q})


@panel_login_required
@permission_required('stock', 'adjust_critical')
def stock_adjust_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    stock = Stock.objects.filter(id_product=product).first()
    form = StockAdjustForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            adjust_stock(
                product,
                form.cleaned_data['delta'],
                actor=get_panel_user(request),
                reason=form.cleaned_data['reason'],
                request=request,
            )
            messages.success(request, 'Остаток скорректирован.')
            return redirect('panel:stock_list')
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else str(exc))
    return render(
        request,
        'panel/warehouse/stock_adjust.html',
        {'form': form, 'product': product, 'stock': stock},
    )


@panel_login_required
@permission_required('stock', 'pick')
def order_pick_view(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('items__id_product'), pk=pk)
    if order.order_status != 'ASSEMBLY':
        messages.error(request, 'Списание доступно только для заказов в статусе «В сборке».')
        return redirect('panel:order_detail', pk=pk)
    actor = get_panel_user(request)
    if request.method == 'POST':
        try:
            for item in order.items.all():
                write_off_for_order_item(
                    item.id_product,
                    item.order_item_quantity,
                    actor=actor,
                    order_id=order.id_order,
                    request=request,
                )
            change_order_status(order, 'PACKED', actor=actor, reason='Сборка завершена', request=request)
            messages.success(request, 'Товары списаны, заказ переведён в «Собран».')
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else str(exc))
        return redirect('panel:order_detail', pk=pk)
    return render(request, 'panel/warehouse/pick_confirm.html', {'order': order})


@panel_login_required
@permission_required('payments', 'view')
def payment_list_view(request):
    qs = Payment.objects.select_related('id_order').order_by('-created_at')
    status = request.GET.get('status')
    if status:
        qs = qs.filter(payment_status=status)
    return render(request, 'panel/finance/payment_list.html', {'page_obj': _paginate(request, qs), 'status': status})


@panel_login_required
@permission_required('returns', 'view')
def return_list_view(request):
    qs = Return.objects.select_related('id_order', 'id_user').order_by('-created_at')
    return render(request, 'panel/finance/return_list.html', {'page_obj': _paginate(request, qs)})


@panel_login_required
@permission_required('reviews', 'view')
def review_list_view(request):
    qs = Review.objects.select_related('id_product', 'id_user').order_by('-created_at')
    status = request.GET.get('status')
    if status:
        qs = qs.filter(review_status=status)
    return render(request, 'panel/reviews/list.html', {'page_obj': _paginate(request, qs), 'status': status})


@panel_login_required
@permission_required('reviews', 'moderate')
def review_moderate_view(request, pk):
    review = get_object_or_404(Review, pk=pk)
    form = ReviewModerationForm(request.POST or None, instance=review)
    if request.method == 'POST' and form.is_valid():
        before = {'status': review.review_status}
        review = form.save()
        write_audit(
            user=get_panel_user(request),
            object_type='review',
            object_id=review.id_review,
            action='moderate',
            before=before,
            after={'status': review.review_status},
            request=request,
        )
        messages.success(request, 'Статус отзыва обновлён.')
        return redirect('panel:review_list')
    return render(request, 'panel/reviews/moderate.html', {'form': form, 'review': review})


@panel_login_required
@permission_required('audit', 'view')
def audit_list_view(request):
    qs = AuditLog.objects.select_related('id_user').order_by('-created_at')
    object_type = request.GET.get('type')
    if object_type:
        qs = qs.filter(audit_object_type=object_type)
    return render(request, 'panel/audit/list.html', {'page_obj': _paginate(request, qs, 40), 'object_type': object_type})


@panel_login_required
@permission_required('audit', 'export')
def audit_export_view(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="audit_log.csv"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';')
    writer.writerow(
        ['ID', 'Дата', 'Пользователь', 'Объект', 'ID объекта', 'Действие', 'IP', 'До', 'После']
    )
    for row in AuditLog.objects.select_related('id_user').order_by('-created_at')[:5000]:
        writer.writerow(
            [
                row.id_audit,
                row.created_at.isoformat(),
                row.id_user.email if row.id_user else '',
                row.audit_object_type,
                row.object_id or '',
                row.audit_action,
                row.audit_ip or '',
                row.audit_before or '',
                row.audit_after or '',
            ]
        )
    return response


@panel_login_required
@permission_required('system', 'view')
def system_info_view(request):
    from django.conf import settings

    info = {
        'database': settings.DATABASES['default']['NAME'],
        'engine': settings.DATABASES['default']['ENGINE'],
        'backup_policy': [
            'Полный бэкап БД — ежедневно в 02:00 MSK',
            'Инкрементальный — каждые 4 часа',
            'Конфигурации — при каждом релизе',
            'Хранение — 30 дней, ежемесячная проверка restore на тестовом контуре',
            'RPO ≤ 15 мин, RTO ≤ 1 ч для критичных сервисов',
        ],
        'data_path': str(settings.BASE_DIR / 'media'),
        'user_data_tables': ['auth_credentials', 'user_profiles', 'orders', 'payments'],
    }
    return render(request, 'panel/system/info.html', {'info': info})
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719


@panel_login_required
def hotkeys_help_view(request):
    return render(request, 'panel/help/hotkeys.html')
<<<<<<< HEAD


@panel_login_required
def brandbook_view(request):
    return render(request, 'panel/help/brandbook.html')


@panel_login_required
def command_search_view(request):
    """Командная строка Ctrl+K: быстрый переход к товару/заказу/пользователю."""
    from users.permissions import has_permission

    q = request.GET.get('q', '').strip()
    role = request.panel_user.user_role
    results = []
    if len(q) >= 2:
        if has_permission(role, 'products', 'view'):
            for p in Product.objects.filter(Q(product_sku__icontains=q) | Q(product_name__icontains=q))[:6]:
                results.append({'type': 'Товар', 'title': f'{p.product_sku} — {p.product_name}',
                                'url': f'/panel/products/{p.pk}/edit/'})
        if has_permission(role, 'orders', 'view'):
            for o in Order.objects.filter(Q(order_number__icontains=q) | Q(id_user__email__icontains=q))[:6]:
                results.append({'type': 'Заказ', 'title': f'{o.order_number} · {o.total} ₽',
                                'url': f'/panel/orders/{o.pk}/'})
        if has_permission(role, 'users', 'view'):
            for u in AuthCredentials.objects.filter(email__icontains=q)[:4]:
                results.append({'type': 'Пользователь', 'title': u.email, 'url': f'/panel/users/{u.pk}/edit/'})
    return JsonResponse({'results': results})


def permission_denied_view(request, exception=None):
    return render(request, 'panel/403.html', {'message': str(exception or '')}, status=403)
=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
