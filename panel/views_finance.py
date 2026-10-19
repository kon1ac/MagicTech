"""Панель: платежи, сверка с выписками, возвраты."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from panel.decorators import panel_login_required, permission_required
from panel.forms import ManualConfirmForm, RefundForm, ReturnAuditEditForm, ReturnStatusForm, StatementUploadForm
from panel.listing import apply_sorting, default_filter_redirect, list_context, paginate
from shop.models import BankStatementImport, Order, Payment, Return, ReturnReason
from shop.services import imports, payments as payment_service, returns as return_service
from shop.services.audit import object_history
from users.constants import PAYMENT_STATUS_LABELS, RETURN_STATUS_FLOW, RETURN_STATUS_LABELS
from users.permissions import has_permission


@panel_login_required
@permission_required('payments', 'view')
def payment_list_view(request):
    actor = request.panel_user
    if (resp := default_filter_redirect(request, actor, 'payments')):
        return resp
    qs = Payment.objects.select_related('id_order', 'id_order__id_user')
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(payment_status=status)
    provider = request.GET.get('provider', '')
    if provider:
        qs = qs.filter(payment_provider=provider)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(id_order__order_number__icontains=q) | Q(external_id__icontains=q)
                       | Q(payment_uid__icontains=q) if len(q) >= 8 else Q(id_order__order_number__icontains=q))
    qs, keys = apply_sorting(request, qs, {'created': 'created_at', 'amount': 'payment_amount', 'status': 'payment_status',
                                           'order': 'id_order__order_number', 'paid': 'paid_at'}, '-created')
    return render(request, 'panel/finance/payment_list.html', {
        'page_obj': paginate(request, qs, actor), 'status': status, 'provider': provider, 'q': q,
        'status_labels': PAYMENT_STATUS_LABELS, **list_context(request, actor, 'payments', keys)})


@panel_login_required
@permission_required('payments', 'view')
def payment_detail_view(request, pk):
    payment = get_object_or_404(Payment.objects.select_related('id_order', 'id_order__id_user'), pk=pk)
    role = request.panel_user.user_role
    return render(request, 'panel/finance/payment_detail.html', {
        'payment': payment, 'logs': payment.logs.order_by('created_at'), 'status_labels': PAYMENT_STATUS_LABELS,
        'refund_form': RefundForm(initial={'amount': payment.payment_amount - (payment.payment_refund_amount or 0)}),
        'confirm_form': ManualConfirmForm(),
        'can_update': has_permission(role, 'payments', 'update'), 'can_refund': has_permission(role, 'payments', 'refund'),
        'history': object_history('payment', payment.pk),
        'returns': payment.id_order.returns.all(),
    })


@panel_login_required
@permission_required('payments', 'update')
@require_POST
def payment_confirm_view(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    form = ManualConfirmForm(request.POST)
    if form.is_valid():
        try:
            payment_service.confirm_manually(payment, actor=request.panel_user, reason=form.cleaned_data['reason'],
                                             request=request)
            messages.success(request, 'Платёж подтверждён вручную, заказ переведён в «Оплачен».')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    else:
        messages.error(request, 'Укажите основание и подтвердите операцию.')
    return redirect('panel:payment_detail', pk=pk)


@panel_login_required
@permission_required('payments', 'refund')
@require_POST
def payment_refund_view(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    form = RefundForm(request.POST)
    if form.is_valid():
        try:
            payment_service.refund(payment, form.cleaned_data['amount'], actor=request.panel_user,
                                   reason=form.cleaned_data['reason'], request=request)
            messages.success(request, 'Возврат проведён.')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    else:
        messages.error(request, 'Проверьте сумму, причину и подтверждение.')
    return redirect('panel:payment_detail', pk=pk)


# ---------------------------------------------------------------- выписки

@panel_login_required
@permission_required('payments', 'import')
def statement_list_view(request):
    form = StatementUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        upload = form.cleaned_data['file']
        try:
            table = imports.read_table(upload.read(), upload.name)
            mapping = imports.guess_mapping(table.headers, imports.STATEMENT_FIELDS)
            imp = imports.import_bank_statement(table, mapping, actor=request.panel_user, file_name=upload.name,
                                                source=form.cleaned_data['source'], request=request)
            messages.success(request, f'Выписка загружена: строк {imp.rows_total}, сверено {imp.rows_matched}, '
                                      f'несоответствий {imp.rows_mismatched}.')
            return redirect('panel:statement_detail', pk=imp.pk)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    qs = BankStatementImport.objects.select_related('id_user').order_by('-created_at')
    return render(request, 'panel/finance/statement_list.html', {'form': form, 'page_obj': paginate(request, qs, request.panel_user)})


@panel_login_required
@permission_required('payments', 'import')
def statement_detail_view(request, pk):
    imp = get_object_or_404(BankStatementImport, pk=pk)
    lines = imp.lines.select_related('id_order', 'id_payment').order_by('row_number')
    only = request.GET.get('only', '')
    if only == 'problems':
        lines = lines.exclude(match_status='matched')
    return render(request, 'panel/finance/statement_detail.html', {'imp': imp, 'lines': lines, 'only': only})


# ---------------------------------------------------------------- возвраты

@panel_login_required
@permission_required('returns', 'view')
def return_list_view(request):
    actor = request.panel_user
    if (resp := default_filter_redirect(request, actor, 'returns')):
        return resp
    qs = Return.objects.select_related('id_order', 'id_user', 'id_reason')
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(return_status=status)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(id_order__order_number__icontains=q) | Q(id_user__email__icontains=q))
    qs, keys = apply_sorting(request, qs, {'created': 'created_at', 'status': 'return_status', 'amount': 'refund_amount',
                                           'order': 'id_order__order_number'}, '-created')
    return render(request, 'panel/finance/return_list.html', {
        'page_obj': paginate(request, qs, actor), 'status': status, 'q': q, 'status_labels': RETURN_STATUS_LABELS,
        **list_context(request, actor, 'returns', keys)})


@panel_login_required
@permission_required('returns', 'view')
def return_detail_view(request, pk):
    ret = get_object_or_404(Return.objects.select_related('id_order', 'id_user', 'id_reason', 'decided_by'), pk=pk)
    role = request.panel_user.user_role
    can_update = has_permission(role, 'returns', 'update')
    status_form = ReturnStatusForm(request.POST if request.POST.get('form') == 'status' else None,
                                   allowed=RETURN_STATUS_FLOW.get(ret.return_status, set()))
    edit_form = ReturnAuditEditForm(
        request.POST if request.POST.get('form') == 'edit' else None,
        initial={'refund_amount': ret.refund_amount, 'return_description': ret.return_description})
    if request.method == 'POST':
        if not can_update:
            messages.error(request, 'Недостаточно прав.')
            return redirect('panel:return_detail', pk=pk)
        try:
            if request.POST.get('form') == 'status' and status_form.is_valid():
                return_service.change_return_status(ret, status_form.cleaned_data['new_status'], actor=request.panel_user,
                                                    decision=status_form.cleaned_data['decision'], request=request)
                messages.success(request, 'Статус возврата обновлён.')
                return redirect('panel:return_detail', pk=pk)
            if request.POST.get('form') == 'edit' and edit_form.is_valid():
                if ret.is_locked and not has_permission(role, 'returns', 'audit_edit'):
                    raise ValidationError('Аудиторская правка утверждённой заявки доступна администратору.')
                return_service.edit_return(ret, actor=request.panel_user, reason=edit_form.cleaned_data['reason'],
                                           changes={'refund_amount': edit_form.cleaned_data['refund_amount'],
                                                    'return_description': edit_form.cleaned_data['return_description']},
                                           request=request)
                messages.success(request, 'Заявка изменена, версия увеличена.')
                return redirect('panel:return_detail', pk=pk)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    return render(request, 'panel/finance/return_detail.html', {
        'ret': ret, 'items': ret.items.select_related('id_order_item__id_product'), 'status_labels': RETURN_STATUS_LABELS,
        'status_form': status_form, 'edit_form': edit_form, 'can_update': can_update,
        'history': object_history('return', ret.pk), 'payments': ret.id_order.payments.all(),
    })


@panel_login_required
@permission_required('returns', 'create')
def return_create_view(request, order_id):
    """Администратор заводит заявку на возврат за покупателя."""
    order = get_object_or_404(Order.objects.select_related('id_user'), pk=order_id)
    items = [{'item': i, 'available': return_service.returnable_quantity(i)}
             for i in order.items.select_related('id_product')]
    if request.method == 'POST':
        quantities = {}
        for row in items:
            raw = request.POST.get(f'qty_{row["item"].pk}', '0')
            quantities[row['item'].pk] = int(raw) if raw.isdigit() else 0
        reason = ReturnReason.objects.filter(pk=request.POST.get('reason') or 0).first()
        try:
            ret = return_service.create_return(order, user=order.id_user, reason=reason,
                                               description=request.POST.get('description', ''),
                                               quantities=quantities, actor=request.panel_user, request=request)
            messages.success(request, f'Заявка на возврат #{ret.pk} создана.')
            return redirect('panel:return_detail', pk=ret.pk)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    return render(request, 'panel/finance/return_create.html', {
        'order': order, 'items': items, 'reasons': ReturnReason.objects.all()})
