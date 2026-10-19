from django.contrib import admin

from .models import AuthCredentials, UserProfiles


@admin.register(AuthCredentials)
class AuthCredentialsAdmin(admin.ModelAdmin):
    list_display = ('id_user', 'email', 'user_role', 'is_active', 'created_at', 'updated_at')
    list_filter = ('user_role', 'is_active', 'created_at')
    search_fields = ('email',)
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)


@admin.register(UserProfiles)
class UserProfilesAdmin(admin.ModelAdmin):
    list_display = (
        'id_user',
        'profile_first_name',
        'profile_last_name',
        'profile_phone',
        'created_at',
    )
    list_filter = ('created_at',)
    search_fields = (
        'profile_first_name',
        'profile_last_name',
        'profile_phone',
        'id_user__email',
    )
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('id_user',)
<<<<<<< HEAD


from .models import ApiToken, SavedFilter, UserSettings  # noqa: E402


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ('token_name', 'id_user', 'token_prefix', 'token_scopes', 'is_active', 'expires_at', 'last_used_at')
    readonly_fields = ('token_hash', 'token_prefix')


admin.site.register(UserSettings)
admin.site.register(SavedFilter)
=======
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
