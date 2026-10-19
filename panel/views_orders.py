"""Панель: заказы (статусы по регламенту, массовые операции), склад, сборка, печать."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from panel.decorators import panel_login_required, permission_required
from panel.forms import BulkStatusForm, OrderStatusForm, StockAdjustForm, StockReceiptForm
from panel.listing import apply_sorting, default_filter_redirect, list_context, paginate
from shop.models import Order, Product, Stock, StockMovement
from shop.services import exports, orders as order_service, payments as payment_service
from shop.services.audit import object_history, write_audit
from shop.services.stock import adjust_stock, receive_stock, write_off_for_order
from users.constants import ORDER_STATUS_LABELS, PAYMENT_METHOD_LABELS, PAYMENT_STATUS_LABELS
from users.permissions import has_permission

ORDER_SORT = {'number': 'order_number', 'customer': 'id_user__email', 'status': 'order_status',
              'total': 'total', 'created': 'created_at', 'payment': 'order_payment_status', 'channel': 'order_channel'}


def _order_queryset(request):
    q = request.GET.get('q', '').strip()
    qs = Order.objects.select_related('id_user')
    if q:
        qs = qs.filter(Q(order_number__icontains=q) | Q(id_user__email__icontains=q) | Q(contact_phone__icontains=q))
    statuses = [s for s in request.GET.getlist('status') if s in ORDER_STATUS_LABELS]
    if statuses:
        qs = qs.filter(order_status__in=statuses)
    if request.GET.get('payment') in PAYMENT_METHOD_LABELS:
        qs = qs.filter(order_payment_method=request.GET['payment'])
    if request.GET.get('paid') in ('1', '0'):
        qs = qs.filter(order_payment_status='SUCCESS') if request.GET['paid'] == '1' else qs.exclude(order_payment_status='SUCCESS')
    if request.GET.get('from'):
        qs = qs.filter(created_at__date__gte=request.GET['from'])
    if request.GET.get('to'):
        qs = qs.filter(created_at__date__lte=request.GET['to'])
    if request.GET.get('channel'):
        qs = qs.filter(order_channel=request.GET['channel'])
    return qs, q, statuses


@panel_login_required
@permission_required('orders', 'view')
def order_list_view(request):
    actor = request.panel_user
    if (resp := default_filter_redirect(request, actor, 'orders')):
        return resp
    qs, q, statuses = _order_queryset(request)
    qs, keys = apply_sorting(request, qs, ORDER_SORT, '-created')
    quick = [
        ('Новые', 'status=NEW'), ('К подтверждению', 'status=PAID'), ('В сборке', 'status=ASSEMBLY'),
        ('Собраны', 'status=PACKED'), ('Не оплачены', 'paid=0&status=NEW&status=CONFIRMED'),
        ('Отменённые', 'status=CANCELLED'),
    ]
    return render(request, 'panel/orders/list.html', {
        'page_obj': paginate(request, qs, actor), 'q': q, 'statuses': statuses, 'status_labels': ORDER_STATUS_LABELS,
        'payment_labels': PAYMENT_METHOD_LABELS, 'quick_filters': quick, 'channels': ['site', 'mobile', 'marketplace'],
        'bulk_statuses': [(c, l) for c, l in ORDER_STATUS_LABELS.items() if c not in ('PAID', 'RETURNED', 'NEW')],
        **list_context(request, actor, 'orders', keys),
    })


@panel_login_required
@permission_required('orders', 'export')
def order_export_view(request):
    qs, _, _ = _order_queryset(request)
    write_audit(user=request.panel_user, object_type='export', object_id=None, action='orders_csv',
                after={'query': request.GET.urlencode()}, request=request)
    response = HttpResponse(exports.orders_csv(qs.order_by('-created_at')), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="orders.csv"'
    return response


@panel_login_required
@permission_required('orders', 'bulk')
@require_POST
def order_bulk_view(request):
    form = BulkStatusForm(request.POST)
    form.fields['new_status'].choices = list(ORDER_STATUS_LABELS.items())
    back = request.META.get('HTTP_REFERER') or '/panel/orders/'
    if not form.is_valid():
        messages.error(request, 'Выберите заказы, статус и подтвердите массовую операцию.')
        return redirect(back)
    ids = [int(i) for i in form.cleaned_data['ids'].split(',') if i.strip().isdigit()]
    new_status = form.cleaned_data['new_status']
    reason = form.cleaned_data['reason'] or 'Массовая смена статуса'
    ok, failed = 0, []
    for order in Order.objects.filter(pk__in=ids):
        try:
            # каждый заказ — отдельная атомарная операция; ошибка одного не влияет на остальные
            order_service.change_order_status(order, new_status, actor=request.panel_user, reason=reason,
                                              request=request)
            ok += 1
        except ValidationError as exc:
            failed.append(f'{order.order_number}: {exc.messages[0]}')
    if ok:
        messages.success(request, f'Статус изменён у {ok} заказов.')
    for text in failed[:10]:
        messages.error(request, text)
    return redirect(back)


@panel_login_required
@permission_required('orders', 'view')
def order_detail_view(request, pk):
    order = get_object_or_404(Order.objects.select_related('id_user', 'id_user__profile')
                              .prefetch_related('items__id_product'), pk=pk)
    actor = request.panel_user
    role = actor.user_role
    can_change = has_permission(role, 'orders', 'update_status')
    allowed = order_service.allowed_transitions(order)
    if not has_permission(role, 'orders', 'cancel_critical'):
        allowed.discard('CANCELLED')
    form = OrderStatusForm(request.POST or None, allowed=allowed)
    if request.method == 'POST':
        if not can_change:
            messages.error(request, 'Статусы заказов меняет администратор.')
            return redirect('panel:order_detail', pk=pk)
        if form.is_valid():
            try:
                order_service.change_order_status(order, form.cleaned_data['new_status'], actor=actor,
                                                  reason=form.cleaned_data.get('reason') or '', request=request)
                messages.success(request, 'Статус заказа обновлён.')
                return redirect('panel:order_detail', pk=pk)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
    history = list(object_history('order', order.pk))
    return render(request, 'panel/orders/detail.html', {
        'order': order, 'form': form, 'status_labels': ORDER_STATUS_LABELS, 'can_change': can_change and allowed,
        'payment_labels': PAYMENT_METHOD_LABELS, 'payment_status_labels': PAYMENT_STATUS_LABELS,
        'payments': order.payments.all(), 'returns': order.returns.all(), 'promotions': order.order_promotions.select_related('id_promotion'),
        'movements': order.stock_movements.select_related('id_product').order_by('-created_at'),
        'reservations': order.reservations.select_related('id_product'),
        'history': history,
        'can_mark_cod': has_permission(role, 'orders', 'mark_cod_paid') and order.order_payment_method == 'cash_on_delivery'
        and order.order_payment_status != 'SUCCESS' and order.order_status not in ('CANCELLED', 'RETURNED'),
        'can_print': has_permission(role, 'stock', 'print'),
        'can_pick': has_permission(role, 'stock', 'pick') and order.order_status == 'ASSEMBLY',
        'can_return': has_permission(role, 'returns', 'create') and order.order_status == 'COMPLETED',
    })


@panel_login_required
@permission_required('orders', 'mark_cod_paid')
@require_POST
def order_mark_cod_paid_view(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not request.POST.get('confirm'):
        messages.error(request, 'Подтвердите получение оплаты.')
    else:
        try:
            payment_service.mark_cash_on_delivery_paid(order, actor=request.panel_user, request=request)
            messages.success(request, 'Оплата при получении отмечена.')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    return redirect('panel:order_detail', pk=pk)


@panel_login_required
@permission_required('stock', 'print')
def order_invoice_view(request, pk):
    order = get_object_or_404(Order.objects.select_related('id_user'), pk=pk)
    write_audit(user=request.panel_user, object_type='order', object_id=pk, action='print_invoice', request=request)
    response = HttpResponse(exports.invoice_pdf(order), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="invoice_{order.order_number}.pdf"'
    return response


@panel_login_required
@permission_required('stock', 'print')
def order_label_view(request, pk):
    order = get_object_or_404(Order.objects.select_related('id_user'), pk=pk)
    write_audit(user=request.panel_user, object_type='order', object_id=pk, action='print_label', request=request)
    response = HttpResponse(exports.label_pdf(order), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="label_{order.order_number}.pdf"'
    return response


# ---------------------------------------------------------------- сборка

@panel_login_required
@permission_required('stock', 'pick')
def pick_tasks_view(request):
    """Задания на сборку: заказы в статусе ASSEMBLY."""
    qs = Order.objects.filter(order_status='ASSEMBLY').select_related('id_user').prefetch_related('items__id_product')
    qs, keys = apply_sorting(request, qs, {'created': 'created_at', 'number': 'order_number'}, 'created')
    packed = Order.objects.filter(order_status='PACKED', shipped_at__isnull=True).order_by('-updated_at')[:20]
    return render(request, 'panel/warehouse/pick_tasks.html', {
        'page_obj': paginate(request, qs, request.panel_user), 'packed': packed,
        **list_context(request, request.panel_user, 'pick', keys)})


@panel_login_required
@permission_required('stock', 'pick')
@require_http_methods(['GET', 'POST'])
def order_pick_view(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('items__id_product'), pk=pk)
    if order.order_status != 'ASSEMBLY':
        messages.error(request, 'Сборка доступна только для заказов в статусе «В сборке».')
        return redirect('panel:pick_tasks')
    items = list(order.items.select_related('id_product'))
    if request.method == 'POST':
        picked = set(request.POST.getlist('picked'))
        missing = [i.id_product.product_name for i in items if str(i.pk) not in picked]
        if missing:
            messages.error(request, 'Отметьте все отобранные товары: ' + ', '.join(missing))
        elif not request.POST.get('confirm'):
            messages.error(request, 'Подтвердите списание остатков.')
        else:
            try:
                with transaction.atomic():
                    write_off_for_order(order, actor=request.panel_user, request=request)
                    order_service.change_order_status(order, 'PACKED', actor=request.panel_user,
                                                      reason='Сборка завершена', request=request, system=True)
                messages.success(request, f'Заказ {order.order_number} собран, товары списаны. Распечатайте накладную и ярлык.')
                return redirect('panel:order_detail', pk=pk)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
    stocks = {s.id_product_id: s for s in Stock.objects.filter(id_product__in=[i.id_product_id for i in items])}
    rows = [{'item': i, 'stock': stocks.get(i.id_product_id)} for i in items]
    return render(request, 'panel/warehouse/pick_confirm.html', {'order': order, 'rows': rows})


# ---------------------------------------------------------------- склад

@panel_login_required
@permission_required('stock', 'view')
def stock_list_view(request):
    actor = request.panel_user
    if (resp := default_filter_redirect(request, actor, 'stock')):
        return resp
    q = request.GET.get('q', '').strip()
    qs = Stock.objects.select_related('id_product')
    if q:
        qs = qs.filter(Q(id_product__product_sku__icontains=q) | Q(id_product__product_name__icontains=q))
    level = request.GET.get('level', '')
    if level == 'out':
        qs = qs.filter(stock_quantity__lte=0)
    elif level == 'low':
        qs = qs.filter(stock_quantity__gt=0, stock_quantity__lte=5)
    elif level == 'reserved':
        qs = qs.filter(stock_reserved__gt=0)
    qs, keys = apply_sorting(request, qs, {'sku': 'id_product__product_sku', 'name': 'id_product__product_name',
                                           'qty': 'stock_quantity', 'reserved': 'stock_reserved',
                                           'updated': 'updated_at'}, '-updated')
    return render(request, 'panel/warehouse/stock_list.html', {
        'page_obj': paginate(request, qs, actor), 'q': q, 'level': level,
        **list_context(request, actor, 'stock', keys)})


@panel_login_required
@permission_required('stock', 'view')
def movement_list_view(request):
    qs = StockMovement.objects.select_related('id_product', 'id_user', 'id_order')
    mtype = request.GET.get('type', '')
    if mtype:
        qs = qs.filter(movement_type=mtype)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(id_product__product_sku__icontains=q) | Q(document_number__icontains=q))
    qs, keys = apply_sorting(request, qs, {'created': 'created_at', 'type': 'movement_type',
                                           'sku': 'id_product__product_sku'}, '-created')
    return render(request, 'panel/warehouse/movements.html', {
        'page_obj': paginate(request, qs, request.panel_user), 'types': StockMovement.TYPES, 'type': mtype, 'q': q,
        **list_context(request, request.panel_user, 'movements', keys)})


@panel_login_required
@permission_required('stock', 'receipt')
def stock_receipt_view(request):
    initial = {}
    if request.GET.get('product', '').isdigit():
        initial['product'] = request.GET['product']
    form = StockReceiptForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            movement = receive_stock(data['product'], data['quantity'], actor=request.panel_user,
                                     document_number=data['document_number'],
                                     expected_quantity=data['expected_quantity'], reason=data['reason'] or '',
                                     request=request)
            if data['expected_quantity'] is not None and data['expected_quantity'] != data['quantity']:
                messages.warning(request, f'Приход оформлен с расхождением: {movement.movement_reason}')
            else:
                messages.success(request, 'Приход оформлен, остаток обновлён.')
            return redirect('panel:stock_list')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    return render(request, 'panel/form.html', {'form': form, 'title': 'Приход товара (I)', 'back': 'panel:stock_list'})


@panel_login_required
@permission_required('stock', 'adjust_critical')
def stock_adjust_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    stock = Stock.objects.filter(id_product=product).first()
    form = StockAdjustForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            adjust_stock(product, form.cleaned_data['delta'], actor=request.panel_user,
                         reason=form.cleaned_data['reason'], request=request)
            messages.success(request, 'Остаток скорректирован.')
            return redirect('panel:stock_list')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    return render(request, 'panel/warehouse/stock_adjust.html', {
        'form': form, 'product': product, 'stock': stock,
        'history': object_history('stock', stock.pk) if stock else []})
