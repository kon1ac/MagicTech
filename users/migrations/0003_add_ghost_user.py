# Generated migration for ghost user creation

from django.db import migrations


def create_ghost_user(apps, schema_editor):
    AuthCredentials = apps.get_model('users', 'AuthCredentials')
    AuthCredentials.objects.get_or_create(
        email='ghost@system.local',
        defaults={
            'password_hash': '',  # не используется, войти нельзя
            'user_role': 'GHOST',
            'is_active': False,
        },
    )


def remove_ghost_user(apps, schema_editor):
    AuthCredentials = apps.get_model('users', 'AuthCredentials')
    AuthCredentials.objects.filter(email='ghost@system.local').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_usersettings_apitoken_savedfilter'),
    ]

    operations = [
        migrations.RunPython(create_ghost_user, remove_ghost_user),
    ]
