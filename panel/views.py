"""Панель: вход, обзор, пользователи и роли, настройки пользователя, справка."""

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, ProtectedError, Q, Sum
from django.db.models.deletion import RestrictedError
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
from users.constants import ORDER_STATUS_LABELS, ROLE_CHOICES, ROLE_GHOST, ROLE_LABELS
from users.models import AuthCredentials, SavedFilter, UserSettings
from users.permissions import ACTION_LABELS, PERMISSION_MATRIX


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if get_panel_user(request):
        return redirect('panel:dashboard')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = authenticate_credentials(form.cleaned_data['email'], form.cleaned_data['password'])
        if user:
            login_user(request, user)
            write_audit(user=user, object_type='session', object_id=user.id_user, action='login', request=request)
            next_url = request.GET.get('next', '')
            if next_url.startswith('/panel') and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
                return redirect(next_url)
            return redirect('panel:dashboard')
        write_audit(user=None, object_type='session', object_id=None, action='login_failed',
                    after={'email': form.cleaned_data['email']}, request=request)
        messages.error(request, 'Неверный email или пароль, либо нет доступа к панели.')
    return render(request, 'panel/login.html', {'form': form})


@require_POST
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


@panel_login_required
@permission_required('users', 'create')
def user_create_view(request):
    form = UserForm(request.POST or None, actor=request.panel_user)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        write_audit(user=request.panel_user, object_type='user', object_id=user.id_user, action='create',
                    after={'email': user.email, 'role': user.user_role}, request=request)
        messages.success(request, 'Пользователь создан.')
        return redirect('panel:user_list')
    return render(request, 'panel/form.html', {'form': form, 'title': 'Новый пользователь',
                                               'back': 'panel:user_list'})


@panel_login_required
@permission_required('users', 'update')
def user_edit_view(request, pk):
    user = get_object_or_404(AuthCredentials, pk=pk)
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
    if user.user_role == ROLE_GHOST:
        messages.error(request, 'Удаление системной учётной записи запрещено.')
        return redirect('panel:user_list')
    if request.method == 'POST' and request.POST.get('confirm'):
        snapshot = {'email': user.email, 'role': user.user_role}
        try:
            with transaction.atomic():
                # Снимаем RESTRICT-блокировку: заказы и возвраты переезжают на ghost
                moved = user.transfer_orphans_to_ghost()
                user.delete()
            action, text = 'delete', 'Пользователь удалён.'
            after = {'moved_to_ghost': moved} if moved else None
        except (RestrictedError, ProtectedError) as exc:
            # Что-то не учтено в переносе — не ломаем историю, просто деактивируем
            user.is_active = False
            user.save(update_fields=['is_active', 'updated_at'])
            action, text = 'deactivate', f'У пользователя есть зависимости — учётная запись деактивирована. ({exc})'
            after = None
        write_audit(user=request.panel_user, object_type='user', object_id=pk, action=action,
                    before=snapshot, after=after, request=request)
        messages.success(request, text)
        return redirect('panel:user_list')
    return render(request, 'panel/confirm.html', {
        'title': 'Удаление пользователя', 'object': user.email, 'back': 'panel:user_list',
        'text': 'Учётная запись будет удалена. Заказы и возвраты перейдут на системную учётную запись.'})


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


@panel_login_required
def hotkeys_help_view(request):
    return render(request, 'panel/help/hotkeys.html')


@panel_login_required
def brandbook_view(request):
    return render(request, 'panel/help/brandbook.html')


@panel_login_required
def command_search_view(request):
    """Командная строка Alt+K: быстрый переход к товару/заказу/пользователю."""
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
