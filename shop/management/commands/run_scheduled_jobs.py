"""Планировщик регламентных заданий СУБД. Запускать раз в минуту:
  Linux (cron):  * * * * * cd /path/MagicTech && venv/bin/python manage.py run_scheduled_jobs
  Windows:       schtasks /Create /SC MINUTE /TN MagicTechJobs /TR "...\\venv\\Scripts\\python.exe manage.py run_scheduled_jobs"
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from shop.models import ScheduledJob
from shop.services import dbadmin


class Command(BaseCommand):
    help = 'Выполняет регламентные задания, расписание которых совпадает с текущей минутой'

    def add_arguments(self, parser):
        parser.add_argument('--job', help='Выполнить конкретное задание немедленно (job_code)')

    def handle(self, *args, **options):
        dbadmin.ensure_default_jobs()
        now = timezone.localtime().replace(second=0, microsecond=0)
        if options['job']:
            jobs = ScheduledJob.objects.filter(job_code=options['job'])
        else:
            jobs = [j for j in ScheduledJob.objects.filter(is_enabled=True) if dbadmin.cron_matches(j.job_schedule, now)
                    and not (j.last_run_at and timezone.localtime(j.last_run_at).replace(second=0, microsecond=0) == now)]
        for job in jobs:
            job = dbadmin.run_job(job)
            self.stdout.write(f'[{job.last_status}] {job.job_code}: {job.last_output}')
