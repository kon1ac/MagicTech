"""Публичная часть: витрина, карточка товара, корзина, оформление, оплата, личный кабинет."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from shop.models import Order, Product, Return, ReturnReason, Review, Wishlist
from shop.services import (
    cart as cart_service,
    catalog,
    orders as order_service,
    payments as payment_service,
    returns as return_service,
    reviews as review_service,
)
from shop.services.audit import write_audit
from shop.services.login_guard import store_login_guard
from store.forms import CheckoutForm, LoginForm, ProfileForm, QuestionForm, RegisterForm, ReviewForm
from users.auth_session import authenticate_credentials, get_current_user, login_user, logout_user
from users.constants import (
    ORDER_STATUS_LABELS,
    PAYMENT_METHOD_LABELS,
    PAYMENT_STATUS_LABELS,
    RETURN_STATUS_LABELS,
    ROLE_CUSTOMER,
)
from users.models import AuthCredentials, UserProfiles


def _session_key(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def _cart(request, create=True):
    user = get_current_user(request)
    return cart_service.get_cart(user=user, session_key=None if user else _session_key(request), create=create)


def login_required_store(view):
    def wrapper(request, *args, **kwargs):
        user = get_current_user(request)
        if not user:
            return redirect(f'/account/login/?next={request.get_full_path()}')
        request.store_user = user
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


# ---------------------------------------------------------------- каталог

def catalog_view(request, slug=None):
    params = request.GET.copy()
    if slug:
        params['category'] = slug
    filters = catalog.parse_filters(params)
    qs, category, facets = catalog.search(filters)
    if filters['category'] and category is None:
        raise Http404('Категория не найдена')
    page = Paginator(qs.prefetch_related('media'), 50).get_page(request.GET.get('page'))
    user = get_current_user(request)
    wishlist = set(Wishlist.objects.filter(id_user=user).values_list('id_product', flat=True)) if user else set()
    query = request.GET.copy()
    query.pop('page', None)
    return render(request, 'store/catalog.html', {
        'page_obj': page, 'filters': filters, 'facets': facets, 'category': category,
        'breadcrumbs': category.ancestors() if category else [], 'tree': catalog.category_tree(),
        'sort_labels': catalog.SORT_LABELS, 'wishlist': wishlist, 'query': query.urlencode(),
        'selected_brands': set(int(b) for b in filters['brands']),
    })


def product_view(request, sku):
    product = get_object_or_404(
        catalog.base_queryset().select_related('id_category__id_parent__id_parent', 'id_unit')
        .prefetch_related('media'), product_sku=sku)
    user = get_current_user(request)
    reviews = (Review.objects.filter(id_product=product, review_status='approved')
               .select_related('id_user__profile').order_by('-created_at'))
    char_names = catalog.filterable_characteristics()
    from shop.models import Characteristic

    char_names.update({c.char_code: c.char_name for c in Characteristic.objects.all()})
    return render(request, 'store/product.html', {
        'product': product, 'images': product.media.all(),
        'characteristics': [(char_names.get(k, k), v) for k, v in (product.product_characteristics or {}).items()],
        'reviews': reviews.filter(review_type='review'), 'questions': reviews.filter(review_type='question'),
        'recommendations': catalog.also_bought(product),
        'can_review': bool(user and review_service.purchased_order(user, product)
                           and not Review.objects.filter(id_user=user, id_product=product, review_type='review').exists()),
        'in_wishlist': bool(user and Wishlist.objects.filter(id_user=user, id_product=product).exists()),
        'review_form': ReviewForm(), 'question_form': QuestionForm(),
        'breadcrumbs': product.id_category.ancestors() if product.id_category else [],
    })


@require_POST
def product_review_view(request, sku):
    user = get_current_user(request)
    if not user:
        return redirect(f'/account/login/?next=/product/{sku}/')
    product = get_object_or_404(Product, product_sku=sku, is_active=True)
    is_question = request.POST.get('kind') == 'question'
    form = QuestionForm(request.POST) if is_question else ReviewForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            review_service.create_review(user, product, rating=form.cleaned_data.get('rating'),
                                         text=form.cleaned_data['text'], photo=form.cleaned_data.get('photo'),
                                         is_question=is_question, request=request)
            messages.success(request, 'Спасибо! Публикация — после модерации.')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    else:
        messages.error(request, 'Проверьте заполнение формы.')
    return redirect('store:product', sku=sku)


@require_POST
def wishlist_toggle_view(request, sku):
    user = get_current_user(request)
    if not user:
        return redirect(f'/account/login/?next=/product/{sku}/')
    product = get_object_or_404(Product, product_sku=sku)
    # Сначала удаляем: delete() атомарен и идемпотентен, а проверка «есть ли
    # запись» через filter().first() + create() на двойной клик упиралась в
    # UniqueConstraint wishlist_unique и отдавала 500.
    deleted, _ = Wishlist.objects.filter(id_user=user, id_product=product).delete()
    if deleted:
        messages.info(request, 'Удалено из избранного.')
    else:
        try:
            Wishlist.objects.create(id_user=user, id_product=product)
        except IntegrityError:
            pass  # параллельный запрос уже добавил — это и есть нужный результат
        messages.success(request, 'Добавлено в избранное.')
    return redirect(_safe_next(request, f'/product/{sku}/'))


def _safe_next(request, default):
    nxt = request.POST.get('next') or request.GET.get('next') or ''
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}) and nxt.startswith('/'):
        return nxt
    return default


# ---------------------------------------------------------------- корзина

def _cart_partial(request, cart):
    """Тело drawer-корзины: partial для fetch-обновлений (?drawer=1)."""
    totals = cart_service.totals(cart) if cart else None
    return render(request, 'store/_cart_body.html', {
        'cart': cart, 'totals': totals,
        'expires_at': cart_service.reservation_expires_at(cart) if cart else None,
    })


def cart_view(request):
    cart = _cart(request, create=False)
    if request.GET.get('drawer'):
        return _cart_partial(request, cart)
    totals = cart_service.totals(cart) if cart else None
    return render(request, 'store/cart.html', {
        'cart': cart, 'totals': totals,
        'expires_at': cart_service.reservation_expires_at(cart) if cart else None,
        'items': {i.id_product_id: i for i in cart.items.all()} if cart else {},
    })


@require_POST
def cart_add_view(request):
    product = get_object_or_404(Product, product_sku=request.POST.get('sku', ''), is_active=True)
    try:
        qty = int(request.POST.get('quantity', 1))
        cart_service.add_item(_cart(request), product, qty)
        messages.success(request, f'«{product.product_name}» в корзине. Товар зарезервирован на 20 минут.')
    except (ValueError, ValidationError) as exc:
        messages.error(request, exc.messages[0] if isinstance(exc, ValidationError) else 'Некорректное количество.')
    return redirect(_safe_next(request, '/cart/'))


@require_POST
def cart_update_view(request):
    cart = _cart(request)
    product = get_object_or_404(Product, product_sku=request.POST.get('sku', ''))
    try:
        cart_service.set_quantity(cart, product, int(request.POST.get('quantity', 0)))
    except (ValueError, ValidationError) as exc:
        messages.error(request, exc.messages[0] if isinstance(exc, ValidationError) else 'Некорректное количество.')
    # drawer корзины меняет количество через fetch — ему нужен свежий HTML тела
    if request.headers.get('X-Requested-With') == 'fetch':
        return _cart_partial(request, cart)
    return redirect('store:cart')


@require_POST
def cart_promo_view(request):
    cart = _cart(request)
    code = request.POST.get('promo_code', '').strip().upper()[:50]
    if request.POST.get('remove'):
        code = ''
    if code:
        _, error = cart_service.pricing.validate_promo_code(code, cart_service.cart_lines(cart))
        if error:
            messages.error(request, error)
            return redirect('store:cart')
        messages.success(request, 'Промокод применён.')
    cart.cart_promo_code = code or None
    cart.save(update_fields=['cart_promo_code', 'updated_at'])
    return redirect('store:cart')


@login_required_store
@require_http_methods(['GET', 'POST'])
def checkout_view(request):
    user = request.store_user
    cart = _cart(request, create=False)
    if not cart or not cart.items.exists():
        messages.info(request, 'Корзина пуста.')
        return redirect('store:catalog')
    profile = getattr(user, 'profile', None)
    form = CheckoutForm(request.POST or None, initial={
        'delivery_address': getattr(profile, 'profile_address', '') or '',
        'contact_phone': getattr(profile, 'profile_phone', '') or ''})
    totals = cart_service.totals(cart)
    if request.method == 'POST' and form.is_valid():
        try:
            order, payment = order_service.checkout(
                cart, user=user, payment_method=form.cleaned_data['payment_method'],
                offer_accepted=form.cleaned_data['offer_accepted'],
                delivery_address=form.cleaned_data['delivery_address'],
                contact_phone=form.cleaned_data['contact_phone'], comment=form.cleaned_data['comment'],
                request=request)
        except ValidationError as exc:
            messages.error(request, f'Заказ не оформлен: {exc.messages[0]}')
        else:
            if payment:
                return redirect('store:pay', uid=payment.payment_uid)
            messages.success(request, f'Заказ {order.order_number} оформлен. Оплата при получении.')
            return redirect('store:account_order', number=order.order_number)
    return render(request, 'store/checkout.html', {'form': form, 'totals': totals, 'cart': cart})


@login_required_store
@require_http_methods(['GET', 'POST'])
def pay_view(request, uid):
    """Имитация платёжной страницы ЮKassa. Кнопки формируют подписанный веб-хук,
    который обрабатывается тем же кодом, что и реальный callback /api/v1/payments/yookassa/webhook/."""
    from shop.models import Payment

    payment = get_object_or_404(Payment.objects.select_related('id_order'), payment_uid=uid,
                                id_order__id_user=request.store_user)
    if request.method == 'POST' and payment.payment_status == 'PENDING':
        event = 'payment.succeeded' if request.POST.get('result') == 'success' else 'payment.canceled'
        body = payment_service.build_webhook(payment, event)
        try:
            payment_service.process_webhook(body, payment_service.sign(body), request=request)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            if event == 'payment.succeeded':
                messages.success(request, 'Оплата прошла успешно.')
            else:
                messages.error(request, 'Оплата отклонена, заказ отменён, резерв снят.')
        return redirect('store:account_order', number=payment.id_order.order_number)
    return render(request, 'store/pay.html', {'payment': payment, 'order': payment.id_order})


# ---------------------------------------------------------------- аккаунт

@require_http_methods(['GET', 'POST'])
def login_view(request):
    blocked_for = store_login_guard.lockout_for(request)
    if blocked_for:
        messages.error(request, f'Слишком много неудачных попыток входа. Повторите через {blocked_for} сек.')
        return render(request, 'store/login.html', {'form': LoginForm(), 'next': request.GET.get('next', '')},
                      status=429)
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        guest_key = request.session.session_key
        email = form.cleaned_data['email']
        user = authenticate_credentials(email, form.cleaned_data['password'], staff_only=False)
        if user:
            store_login_guard.reset(email, request)
            login_user(request, user)
            cart_service.merge_session_cart(guest_key, user)
            write_audit(user=user, object_type='session', object_id=user.pk, action='store_login', request=request)
            return redirect(_safe_next(request, '/account/'))
        store_login_guard.register_fail(email, request)
        messages.error(request, 'Неверный email или пароль.')
    return render(request, 'store/login.html', {'form': form, 'next': request.GET.get('next', '')})


@require_http_methods(['GET', 'POST'])
def register_view(request):
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        guest_key = request.session.session_key
        user = AuthCredentials(email=form.cleaned_data['email'], user_role=ROLE_CUSTOMER)
        user.set_password(form.cleaned_data['password'])
        user.save()
        UserProfiles.objects.create(id_user=user, profile_first_name=form.cleaned_data['first_name'],
                                    profile_phone=form.cleaned_data['phone'] or None)
        login_user(request, user)
        cart_service.merge_session_cart(guest_key, user)
        write_audit(user=user, object_type='user', object_id=user.pk, action='register', request=request)
        messages.success(request, 'Добро пожаловать в MagicTech!')
        return redirect(_safe_next(request, '/account/'))
    return render(request, 'store/register.html', {'form': form})


@require_POST
def logout_view(request):
    logout_user(request)
    return redirect('store:catalog')


@login_required_store
def account_view(request):
    user = request.store_user
    profile, _ = UserProfiles.objects.get_or_create(id_user=user)
    form = ProfileForm(request.POST or None, initial={
        'first_name': profile.profile_first_name, 'last_name': profile.profile_last_name,
        'phone': profile.profile_phone, 'address': profile.profile_address})
    if request.method == 'POST' and form.is_valid():
        profile.profile_first_name = form.cleaned_data['first_name'] or None
        profile.profile_last_name = form.cleaned_data['last_name'] or None
        profile.profile_phone = form.cleaned_data['phone'] or None
        profile.profile_address = form.cleaned_data['address'] or None
        profile.save()
        messages.success(request, 'Профиль сохранён.')
        return redirect('store:account')
    return render(request, 'store/account/profile.html', {
        'form': form, 'orders': user.orders.order_by('-created_at')[:5], 'status_labels': ORDER_STATUS_LABELS})


@login_required_store
def account_orders_view(request):
    orders = request.store_user.orders.order_by('-created_at')
    return render(request, 'store/account/orders.html', {
        'page_obj': Paginator(orders, 20).get_page(request.GET.get('page')), 'status_labels': ORDER_STATUS_LABELS})


@login_required_store
def account_order_view(request, number):
    # доступ только к своим заказам: фильтр по владельцу, чужой номер → 404
    order = get_object_or_404(
        Order.objects.prefetch_related(Prefetch('items__id_product')), order_number=number,
        id_user=request.store_user)
    steps = ['NEW', 'PAID', 'CONFIRMED', 'ASSEMBLY', 'PACKED', 'COMPLETED']
    if order.order_payment_method != 'card_online':
        steps.remove('PAID')
    current = steps.index(order.order_status) if order.order_status in steps else -1
    pending = order.payments.filter(payment_status='PENDING').first()
    return render(request, 'store/account/order.html', {
        'order': order, 'status_labels': ORDER_STATUS_LABELS, 'payment_labels': PAYMENT_METHOD_LABELS,
        'payment_status_labels': PAYMENT_STATUS_LABELS, 'steps': [(s, ORDER_STATUS_LABELS[s], i <= current) for i, s in enumerate(steps)],
        'pending_payment': pending, 'returns': order.returns.all(), 'return_labels': RETURN_STATUS_LABELS,
        'can_return': order.order_status == 'COMPLETED',
    })


@login_required_store
@require_POST
def account_order_cancel_view(request, number):
    order = get_object_or_404(Order, order_number=number, id_user=request.store_user)
    if order.order_status not in ('NEW', 'PAID'):
        messages.error(request, 'Заказ уже в работе — отмена через поддержку.')
    else:
        try:
            with transaction.atomic():  # отмена + снятие резерва + возврат денег — одна транзакция
                order_service.change_order_status(order, 'CANCELLED', actor=request.store_user,
                                                  reason='Отменён покупателем', request=request, system=True)
                refundable = order.payments.filter(payment_status='SUCCESS').first()
                if refundable:
                    payment_service.refund(refundable, refundable.payment_amount, actor=request.store_user,
                                           reason='Отмена заказа покупателем', request=request)
            messages.success(request, 'Заказ отменён.' + (' Деньги возвращены на карту.' if refundable else ''))
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    return redirect('store:account_order', number=number)


@login_required_store
def account_return_create_view(request, number):
    order = get_object_or_404(Order, order_number=number, id_user=request.store_user)
    items = [{'item': i, 'available': return_service.returnable_quantity(i)}
             for i in order.items.select_related('id_product')]
    if request.method == 'POST':
        quantities = {}
        for row in items:
            raw = request.POST.get(f'qty_{row["item"].pk}', '0')
            quantities[row['item'].pk] = int(raw) if raw.isdigit() else 0
        reason = ReturnReason.objects.filter(pk=request.POST.get('reason') or 0).first()
        try:
            return_service.create_return(order, user=request.store_user, reason=reason,
                                         description=request.POST.get('description', '')[:2000],
                                         quantities=quantities, photo=request.FILES.get('photo'), request=request)
            messages.success(request, 'Заявка на возврат отправлена.')
            return redirect('store:account_returns')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    return render(request, 'store/account/return_create.html', {
        'order': order, 'items': items, 'reasons': ReturnReason.objects.all()})


@login_required_store
def account_returns_view(request):
    returns = Return.objects.filter(id_user=request.store_user).select_related('id_order').order_by('-created_at')
    return render(request, 'store/account/returns.html', {'returns': returns, 'status_labels': RETURN_STATUS_LABELS})


@login_required_store
def account_reviews_view(request):
    reviews = Review.objects.filter(id_user=request.store_user).select_related('id_product').order_by('-created_at')
    return render(request, 'store/account/reviews.html', {'reviews': reviews})


@login_required_store
def account_wishlist_view(request):
    ids = Wishlist.objects.filter(id_user=request.store_user).values('id_product')
    products = catalog.base_queryset().filter(pk__in=ids)
    return render(request, 'store/account/wishlist.html', {'products': products})


def offer_view(request):
    return render(request, 'store/offer.html')
