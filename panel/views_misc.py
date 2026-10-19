"""Панель: отзывы, отчёты, импорт/экспорт, аудит."""

import csv
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from panel.decorators import panel_login_required, permission_required
from panel.forms import ImportUploadForm, ReviewModerationForm
from panel.listing import apply_sorting, default_filter_redirect, list_context, paginate
from shop.models import AuditLog, ImportJob, Review
from shop.services import exports, imports, reports, reviews as review_service
from shop.services.audit import write_audit
from users.constants import REVIEW_STATUS_LABELS

# ---------------------------------------------------------------- отзывы


@panel_login_required
@permission_required('reviews', 'view')
def review_list_view(request):
    actor = request.panel_user
    if (resp := default_filter_redirect(request, actor, 'reviews')):
        return resp
    qs = Review.objects.select_related('id_product', 'id_user')
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(review_status=status)
    rtype = request.GET.get('type', '')
    if rtype:
        qs = qs.filter(review_type=rtype)
    if request.GET.get('unanswered') == '1':
        qs = qs.filter(seller_answer__isnull=True)
    qs, keys = apply_sorting(request, qs, {'created': 'created_at', 'rating': 'review_rating',
                                           'product': 'id_product__product_name', 'status': 'review_status'}, '-created')
    return render(request, 'panel/reviews/list.html', {
        'page_obj': paginate(request, qs, actor), 'status': status, 'type': rtype,
        'status_labels': REVIEW_STATUS_LABELS, **list_context(request, actor, 'reviews', keys)})


@panel_login_required
@permission_required('reviews', 'moderate')
def review_moderate_view(request, pk):
    review = get_object_or_404(Review.objects.select_related('id_product', 'id_user', 'id_order'), pk=pk)
    form = ReviewModerationForm(request.POST or None, initial={'review_status': review.review_status,
                                                               'seller_answer': review.seller_answer})
    if request.method == 'POST' and form.is_valid():
        try:
            if form.cleaned_data['review_status'] != review.review_status:
                review_service.moderate(review, form.cleaned_data['review_status'], actor=request.panel_user,
                                        request=request)
            answer = (form.cleaned_data['seller_answer'] or '').strip()
            if answer and answer != (review.seller_answer or ''):
                review_service.answer(review, answer, actor=request.panel_user, request=request)
            messages.success(request, 'Отзыв обработан, рейтинг товара пересчитан.')
            return redirect('panel:review_list')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
    from shop.services.audit import object_history

    return render(request, 'panel/reviews/moderate.html', {'form': form, 'review': review,
                                                           'history': object_history('review', review.pk)})


# ---------------------------------------------------------------- отчёты

REPORT_EXPORTS = {
    'sales': ('Период;Выручка;Заказов;Средний чек', lambda d: [[r['period'], r['revenue'], r['orders'], r['avg_check']] for r in d['sales']['rows']]),
    'top': ('Артикул;Товар;Выручка;Кол-во;Маржа;Маржа %;Возвраты', lambda d: [[r['sku'], r['name'], r['revenue'], r['qty'], r['margin'], r['margin_pct'], r['returns']] for r in d['top']]),
    'finance': ('Показатель;Сумма', lambda d: [['Начислено', d['finance']['accrued']], ['Оплачено', d['finance']['paid']], ['Возвраты', d['finance']['refunds']], ['Комиссии', d['finance']['commission']], ['Нетто', d['finance']['net']]]),
    'statuses': ('Статус;Количество', lambda d: [[r['label'], r['count']] for r in d['statuses']['by_status']] + [['Задержаны (>3 дн.)', d['statuses']['delayed']], ['Просрочена оплата', d['statuses']['overdue']]]),
    'stock': ('Артикул;Товар;Остаток;Резерв;Доступно;Продано за 30 дн.;Оборачиваемость, дн.;Неликвид', lambda d: [[r['sku'], r['name'], r['quantity'], r['reserved'], r['available'], r['sold'], r['turnover_days'] or '', 'да' if r['illiquid'] else ''] for r in d['stock']['rows']]),
}


def _report_data(request):
    date_from, date_to = reports.period_bounds(request.GET)
    group = request.GET.get('group', 'day') if request.GET.get('group') in ('day', 'week', 'month') else 'day'
    top_by = request.GET.get('top_by', 'revenue')
    return {
        'date_from': date_from, 'date_to': date_to, 'group': group, 'top_by': top_by,
        'sales': reports.sales_by_period(date_from, date_to, group),
        'top': reports.top_products(date_from, date_to, top_by),
        'finance': reports.financial(date_from, date_to),
        'statuses': reports.order_statuses(),
        'stock': reports.stock_turnover(),
    }


@panel_login_required
@permission_required('reports', 'view')
def reports_view(request):
    data = _report_data(request)
    charts = {
        'sales': {'labels': [str(r['period']) for r in data['sales']['rows']],
                  'revenue': [float(r['revenue']) for r in data['sales']['rows']],
                  'orders': [r['orders'] for r in data['sales']['rows']]},
        'top': {'labels': [r['name'][:28] for r in data['top']], 'values': [float(r[data['top_by']]) for r in data['top']]},
        'finance': {'labels': ['Оплачено', 'Возвраты', 'Комиссии', 'Нетто'],
                    'values': [float(data['finance'][k]) for k in ('paid', 'refunds', 'commission', 'net')]},
        'statuses': {'labels': [r['label'] for r in data['statuses']['by_status']],
                     'values': [r['count'] for r in data['statuses']['by_status']]},
        'stock': {'labels': [r['sku'] for r in sorted(data['stock']['rows'], key=lambda r: -r['quantity'])[:20]],
                  'qty': [r['quantity'] for r in sorted(data['stock']['rows'], key=lambda r: -r['quantity'])[:20]],
                  'reserved': [r['reserved'] for r in sorted(data['stock']['rows'], key=lambda r: -r['quantity'])[:20]]},
    }
    return render(request, 'panel/reports/index.html', {**data, 'charts': charts})


@panel_login_required
@permission_required('reports', 'export')
def report_export_view(request, kind):
    if kind not in REPORT_EXPORTS:
        raise Http404
    data = _report_data(request)
    header, rows = REPORT_EXPORTS[kind]
    write_audit(user=request.panel_user, object_type='export', object_id=None, action=f'report_{kind}', request=request)
    response = HttpResponse(exports.csv_bytes(header.split(';'), rows(data)), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="report_{kind}_{data["date_from"]}_{data["date_to"]}.csv"'
    return response


# ---------------------------------------------------------------- импорт / экспорт

FIELDS_BY_KIND = {'products': imports.PRODUCT_FIELDS, 'stock': imports.STOCK_FIELDS, 'prices': imports.PRICE_FIELDS}
RUNNERS = {'products': imports.import_products, 'stock': imports.import_stock, 'prices': imports.import_prices}
PERMS = {'products': ('products', 'import'), 'stock': ('stock', 'import'), 'prices': ('prices', 'import')}


def _upload_dir() -> Path:
    path = Path(settings.MEDIA_ROOT) / 'imports'
    path.mkdir(parents=True, exist_ok=True)
    return path


@panel_login_required
@permission_required('products', 'import')
def io_index_view(request):
    from users.permissions import has_permission

    form = ImportUploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        kind = form.cleaned_data['kind']
        if not has_permission(request.panel_user.user_role, *PERMS[kind]):
            messages.error(request, 'Недостаточно прав для этого вида импорта.')
            return redirect('panel:io_index')
        upload = form.cleaned_data['file']
        token = uuid.uuid4().hex
        suffix = '.xlsx' if upload.name.lower().endswith('.xlsx') else '.csv'
        (_upload_dir() / f'{token}{suffix}').write_bytes(upload.read())
        request.session['import_upload'] = {'token': token, 'suffix': suffix, 'name': upload.name, 'kind': kind}
        return redirect('panel:io_mapping')
    jobs = ImportJob.objects.select_related('id_user').order_by('-created_at')
    return render(request, 'panel/io/index.html', {'form': form, 'page_obj': paginate(request, jobs, request.panel_user)})


@panel_login_required
@permission_required('products', 'import')
def io_mapping_view(request):
    """Шаг 2: предпросмотр и сопоставление колонок. Шаг 3 (POST): валидация и транзакционная запись."""
    upload = request.session.get('import_upload')
    if not upload:
        return redirect('panel:io_index')
    path = _upload_dir() / f'{upload["token"]}{upload["suffix"]}'
    if not path.exists():
        messages.error(request, 'Файл загрузки не найден, загрузите его снова.')
        return redirect('panel:io_index')
    try:
        table = imports.read_table(path.read_bytes(), upload['name'])
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
        return redirect('panel:io_index')
    fields = FIELDS_BY_KIND[upload['kind']]
    mapping = imports.guess_mapping(table.headers, fields)
    if request.method == 'POST':
        mapping = {}
        for key in fields:
            raw = request.POST.get(f'map_{key}', '')
            mapping[key] = int(raw) if raw.isdigit() and int(raw) < len(table.headers) else None
        try:
            kwargs = {'actor': request.panel_user, 'file_name': upload['name'], 'request': request}
            if upload['kind'] == 'stock':
                kwargs['default_mode'] = request.POST.get('default_mode', 'set')
            job = RUNNERS[upload['kind']](table, mapping, **kwargs)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            path.unlink(missing_ok=True)
            request.session.pop('import_upload', None)
            if job.import_status == 'success':
                messages.success(request, f'Импорт выполнен: {job.rows_ok} строк за {job.duration_ms} мс.')
            else:
                messages.error(request, f'Импорт отклонён: ошибок в {job.rows_failed} строках. Изменения не внесены.')
            return redirect('panel:io_job', pk=job.pk)
    return render(request, 'panel/io/mapping.html', {
        'upload': upload, 'headers': list(enumerate(table.headers)), 'preview': table.rows[:10],
        'rows_total': len(table.rows),
        'fields': [(key, label, mapping.get(key)) for key, (label, _) in fields.items()],
    })


@panel_login_required
@permission_required('products', 'import')
def io_job_view(request, pk):
    job = get_object_or_404(ImportJob, pk=pk)
    if request.GET.get('format') == 'csv':
        response = HttpResponse('﻿' + imports.import_job_errors_csv(job), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="import_{job.pk}_errors.csv"'
        return response
    return render(request, 'panel/io/job.html', {'job': job})


@panel_login_required
@permission_required('products', 'export')
def export_catalog_view(request, fmt):
    write_audit(user=request.panel_user, object_type='export', object_id=None, action=f'catalog_{fmt}', request=request)
    if fmt == 'xml':
        response = HttpResponse(exports.catalog_xml(request.build_absolute_uri('/').rstrip('/')),
                                content_type='application/xml; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="catalog.xml"'
    else:
        response = HttpResponse(exports.catalog_csv(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="catalog.csv"'
    return response


@panel_login_required
@permission_required('products', 'import')
def import_template_view(request, kind):
    samples = {
        'products': (['sku', 'name', 'price', 'category', 'brand', 'stock', 'characteristics', 'description', 'ean'],
                     [['KB-NEW-001', 'Клавиатура Example TKL', '4990', 'Механические клавиатуры', 'Logitech', '15',
                       'connection=USB;color=Чёрный;backlight=RGB', 'Компактная механика', '4601234567890']]),
        'stock': (['sku', 'quantity', 'mode'], [['KB-NEW-001', '20', 'set']]),
        'prices': (['sku', 'price'], [['KB-NEW-001', '4790']]),
        'statement': (['date', 'purpose', 'amount'], [['15.10.2026', 'Оплата заказа MT-261015-000001', '4990.00']]),
    }
    if kind not in samples:
        raise Http404
    header, rows = samples[kind]
    response = HttpResponse(exports.csv_bytes(header, rows), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="template_{kind}.csv"'
    return response


# ---------------------------------------------------------------- аудит

def _audit_queryset(request):
    qs = AuditLog.objects.select_related('id_user')
    for param, field in (('type', 'audit_object_type'), ('action', 'audit_action')):
        if request.GET.get(param):
            qs = qs.filter(**{field: request.GET[param]})
    if request.GET.get('object_id', '').isdigit():
        qs = qs.filter(object_id=int(request.GET['object_id']))
    if request.GET.get('user'):
        qs = qs.filter(id_user__email__icontains=request.GET['user'])
    if request.GET.get('ip'):
        qs = qs.filter(audit_ip=request.GET['ip'])
    if request.GET.get('from'):
        qs = qs.filter(created_at__date__gte=request.GET['from'])
    if request.GET.get('to'):
        qs = qs.filter(created_at__date__lte=request.GET['to'])
    return qs


@panel_login_required
@permission_required('audit', 'view')
def audit_list_view(request):
    actor = request.panel_user
    qs, keys = apply_sorting(request, _audit_queryset(request), {
        'created': 'created_at', 'type': 'audit_object_type', 'action': 'audit_action', 'user': 'id_user__email'}, '-created')
    types = AuditLog.objects.order_by().values_list('audit_object_type', flat=True).distinct()
    return render(request, 'panel/audit/list.html', {
        'page_obj': paginate(request, qs, actor), 'types': sorted(set(types)), 'params': request.GET,
        **list_context(request, actor, 'audit', keys)})


@panel_login_required
@permission_required('audit', 'export')
def audit_export_view(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="audit_log.csv"'
    response.write('﻿')
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['ID', 'Дата', 'Пользователь', 'Объект', 'ID объекта', 'Действие', 'Причина', 'IP', 'User-Agent',
                     'До', 'После'])
    for row in _audit_queryset(request).order_by('-created_at')[:50000].iterator(chunk_size=2000):
        writer.writerow([row.id_audit, row.created_at.isoformat(), row.id_user.email if row.id_user else '',
                         row.audit_object_type, row.object_id or '', row.audit_action, row.audit_reason or '',
                         row.audit_ip or '', row.audit_user_agent or '', row.audit_before or '', row.audit_after or ''])
    write_audit(user=request.panel_user, object_type='export', object_id=None, action='audit_csv',
                after={'query': request.GET.urlencode()}, request=request)
    return response
