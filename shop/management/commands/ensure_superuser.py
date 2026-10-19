"""Создаёт/обновляет суперпользователя Django Admin (/admin/) без интерактивного ввода."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Создаёт суперпользователя Django: --username Magic --password 123'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='Magic')
        parser.add_argument('--password', default='123')
        parser.add_argument('--email', default='')

    def handle(self, *args, **options):
        User = get_user_model()
        user, created = User.objects.get_or_create(username=options['username'], defaults={'email': options['email']})
        user.is_staff = user.is_superuser = user.is_active = True
        user.set_password(options['password'])
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Суперпользователь {user.username} {"создан" if created else "обновлён"}.'))
