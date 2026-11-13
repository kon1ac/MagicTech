from django.db import migrations, models


def encrypt_existing_profiles(apps, schema_editor):
    UserProfiles = apps.get_model('users', 'UserProfiles')
    from shop.services.crypto import ensure_encrypted

    fields = ('profile_first_name', 'profile_last_name', 'profile_phone', 'profile_address')
    for profile in UserProfiles.objects.all().iterator():
        changed = False
        for field in fields:
            raw = getattr(profile, field)
            enc = ensure_encrypted(raw)
            if enc != raw:
                setattr(profile, field, enc)
                changed = True
        if changed:
            profile.save(update_fields=list(fields) + ['updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_add_ghost_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='authcredentials',
            name='deactivation_reason',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
        migrations.AddField(
            model_name='authcredentials',
            name='deactivated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userprofiles',
            name='pdn_consent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='userprofiles',
            name='pdn_consent_version',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.AlterField(
            model_name='userprofiles',
            name='profile_first_name',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AlterField(
            model_name='userprofiles',
            name='profile_last_name',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.AlterField(
            model_name='userprofiles',
            name='profile_phone',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.RunPython(encrypt_existing_profiles, migrations.RunPython.noop),
    ]
