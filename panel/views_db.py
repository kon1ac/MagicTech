"""Панель: контур администратора БД. Каждое обращение пишется в аудит; вне DEBUG — только HTTPS."""

from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from panel.decorators import panel_login_required, permission_required, secure_channel_required
from panel.forms import ApiTokenForm, ArchiveGrantForm, RestoreForm
from panel.listing import paginate
from shop.models import ArchiveAccessGrant, ArchivedOrder, AuditLog, BackupRecord, ScheduledJob
from shop.services import dbadmin
from shop.services.audit import write_audit
from users.constants import API_SCOPES
from users.models import ApiToken


def db_access_audited(view_func):
    """Обязательный аудит доступа к продовой БД."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        write_audit(user=request.panel_user, object_type='db_access', object_id=None, action=request.method.lower(),
                    after={'path': request.path, 'secure': request.is_secure()}, request=request)
        return view_func(request, *args, **kwargs)

    return wrapper


def db_view(resource_action):
    def decorator(view_func):
        return panel_login_required(permission_required('db', resource_action)(
            secure_channel_required(db_access_audited(view_func))))
    return decorator


@db_view('view')
def db_overview_view(request):
    return render(request, 'panel/db/overview.html', {
        'info': dbadmin.db_characteristics(), 'user_data': dbadmin.USER_DATA_MAP,
        'access_log': AuditLog.objects.filter(audit_object_type='db_access').select_related('id_user').order_by('-created_at')[:15],
    })


@db_view('view')
def db_schema_view(request):
    return render(request, 'panel/db/schema.html', {
        'migrations': dbadmin.migrations_state(), 'indexes': dbadmin.indexes(),
        'grants': dbadmin.roles_and_grants(), 'slow': dbadmin.slow_queries(),
    })


@db_view('backup')
def db_backups_view(request):
    backups = BackupRecord.objects.select_related('id_user').order_by('-created_at')
    return render(request, 'panel/db/backups.html', {
        'page_obj': paginate(request, backups, request.panel_user), 'restore_form': RestoreForm(),
        'policy': [
            ('Полный бэкап БД', 'ежедневно, 02:00 (ночное окно), задание backup-full'),
            ('Инкрементальный', 'каждые 4 часа (транзакционные таблицы) + непрерывный архив WAL'),
            ('Справочники и конфигурации', 'при каждом релизе / изменении схемы, задание backup-schema'),
            ('Хранение', 'не менее 30 дней, ротация — задание cleanup-backups'),
            ('Проверка restore', 'ежемесячно на тестовом контуре (<БД>_restore_test), задание verify-restore'),
            ('RPO / RTO', '≤ 15 минут (archive_timeout = 900 с) / ≤ 1 часа'),
        ],
    })


@db_view('backup')
@require_POST
def db_backup_create_view(request):
    try:
        record = dbadmin.create_backup(request.POST.get('kind', 'full'), actor=request.panel_user, request=request)
        if record.backup_status == 'success':
            messages.success(request, f'Резервная копия создана: {record.file_path}')
        else:
            messages.error(request, f'Ошибка бэкапа: {record.backup_output[-300:]}')
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect('panel:db_backups')


@db_view('backup')
@require_POST
def db_backup_verify_view(request, pk):
    record = get_object_or_404(BackupRecord, pk=pk)
    try:
        record = dbadmin.verify_backup(record, actor=request.panel_user, request=request)
        (messages.success if record.verify_status == 'ok' else messages.error)(
            request, f'Проверка restore: {record.verify_status}')
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect('panel:db_backups')


@db_view('restore')
@require_POST
def db_backup_restore_view(request, pk):
    record = get_object_or_404(BackupRecord, pk=pk)
    form = RestoreForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Подтвердите восстановление и введите имя БД.')
        return redirect('panel:db_backups')
    try:
        dbadmin.restore_backup(record, actor=request.panel_user, confirm_name=form.cleaned_data['confirm_name'],
                               request=request)
        messages.success(request, 'База данных восстановлена из копии.')
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    return redirect('panel:db_backups')


@db_view('jobs')
def db_jobs_view(request):
    dbadmin.ensure_default_jobs()
    return render(request, 'panel/db/jobs.html', {'jobs': ScheduledJob.objects.order_by('job_code')})


@db_view('jobs')
@require_POST
def db_job_action_view(request, pk):
    job = get_object_or_404(ScheduledJob, pk=pk)
    action = request.POST.get('action')
    if action == 'toggle':
        job.is_enabled = not job.is_enabled
        job.save(update_fields=['is_enabled'])
        write_audit(user=request.panel_user, object_type='db_job', object_id=job.pk, action='toggle',
                    after={'enabled': job.is_enabled}, request=request)
        messages.success(request, f'Задание {"включено" if job.is_enabled else "выключено"}.')
    elif action == 'schedule':
        schedule = request.POST.get('schedule', '').strip()
        try:
            dbadmin.cron_matches(schedule, timezone.localtime())
            if len(schedule.split()) != 5:
                raise ValueError
        except (ValueError, IndexError):
            messages.error(request, 'Некорректное cron-выражение (5 полей: мин час день месяц день_недели).')
            return redirect('panel:db_jobs')
        before = job.job_schedule
        job.job_schedule = schedule
        job.save(update_fields=['job_schedule'])
        write_audit(user=request.panel_user, object_type='db_job', object_id=job.pk, action='reschedule',
                    before={'schedule': before}, after={'schedule': schedule}, request=request)
        messages.success(request, 'Расписание обновлено.')
    elif action == 'run':
        job = dbadmin.run_job(job, actor=request.panel_user, request=request)
        (messages.success if job.last_status == 'success' else messages.error)(request, job.last_output[:300])
    return redirect('panel:db_jobs')


@db_view('service_accounts')
def db_service_accounts_view(request):
    form = ApiTokenForm(request.POST or None)
    new_key = None
    if request.method == 'POST' and form.is_valid():
        days = form.cleaned_data['expires_days']
        token, new_key = ApiToken.issue(
            form.cleaned_data['user'], form.cleaned_data['name'], form.cleaned_data['scopes'],
            expires_at=timezone.now() + timedelta(days=days) if days else None)
        write_audit(user=request.panel_user, object_type='api_token', object_id=token.pk, action='issue',
                    after={'name': token.token_name, 'user': token.id_user.email, 'scopes': token.token_scopes},
                    request=request)
        form = ApiTokenForm()
    return render(request, 'panel/db/service_accounts.html', {
        'form': form, 'new_key': new_key, 'scopes': API_SCOPES,
        'tokens': ApiToken.objects.select_related('id_user').order_by('-created_at'),
        'grants': dbadmin.roles_and_grants(),
    })


@db_view('service_accounts')
@require_POST
def db_token_revoke_view(request, pk):
    token = get_object_or_404(ApiToken, pk=pk)
    token.is_active = False
    token.save(update_fields=['is_active'])
    write_audit(user=request.panel_user, object_type='api_token', object_id=token.pk, action='revoke', request=request)
    messages.success(request, 'Токен отозван.')
    return redirect('panel:db_service_accounts')


# ---------------------------------------------------------------- архив

@panel_login_required
@permission_required('archive', 'view')
def archive_view(request):
    from users.permissions import has_permission

    actor = request.panel_user
    if not dbadmin.has_archive_access(actor):
        return render(request, 'panel/db/archive_denied.html', status=403)
    write_audit(user=actor, object_type='archive', object_id=None, action='view',
                after={'query': request.GET.urlencode()}, request=request)
    qs = ArchivedOrder.objects.order_by('-order_created_at')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(order_number__icontains=q) | qs.filter(customer_email__icontains=q)
    role = actor.user_role
    grant_form = ArchiveGrantForm(request.POST or None) if has_permission(role, 'db', 'grant_archive') else None
    if request.method == 'POST' and request.POST.get('form') == 'grant' and grant_form and grant_form.is_valid():
        grant = ArchiveAccessGrant.objects.create(
            id_user=grant_form.cleaned_data['user'], granted_by=actor, grant_reason=grant_form.cleaned_data['reason'],
            expires_at=timezone.now() + timedelta(days=grant_form.cleaned_data['days']))
        write_audit(user=actor, object_type='archive_grant', object_id=grant.pk, action='grant',
                    after={'user': grant.id_user.email, 'expires_at': grant.expires_at}, reason=grant.grant_reason,
                    request=request)
        messages.success(request, 'Доступ к архиву выдан.')
        return redirect('panel:archive')
    if request.method == 'POST' and request.POST.get('form') == 'archive':
        if not has_permission(role, 'db', 'archive') or not request.POST.get('confirm'):
            messages.error(request, 'Недостаточно прав или нет подтверждения.')
        else:
            days = int(request.POST.get('days') or 365)
            count = dbadmin.archive_old_orders(max(days, 30), actor=actor, request=request)
            messages.success(request, f'Заархивировано заказов: {count}.')
        return redirect('panel:archive')
    return render(request, 'panel/db/archive.html', {
        'page_obj': paginate(request, qs, actor), 'q': q, 'grant_form': grant_form,
        'grants': ArchiveAccessGrant.objects.select_related('id_user', 'granted_by').order_by('-created_at')[:20],
        'can_archive': has_permission(role, 'db', 'archive'),
    })


@panel_login_required
@permission_required('archive', 'view')
def archive_detail_view(request, pk):
    if not dbadmin.has_archive_access(request.panel_user):
        return render(request, 'panel/db/archive_denied.html', status=403)
    item = get_object_or_404(ArchivedOrder, pk=pk)
    write_audit(user=request.panel_user, object_type='archive', object_id=item.pk, action='view_detail', request=request)
    return render(request, 'panel/db/archive_detail.html', {'item': item})
