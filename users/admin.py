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
