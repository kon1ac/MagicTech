"""Маршруты MagicTech: витрина (/), панель (/panel/), API (/api/), техническая админка (/admin/)."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'MagicTech — техническая админка Django'
admin.site.site_title = 'MagicTech Admin'
admin.site.index_title = 'Модели и миграции'

urlpatterns = [
    path('panel/', include('panel.urls')),
    path('api/', include('api.urls')),
    path('admin/', admin.site.urls),
    path('', include('store.urls')),
]

handler403 = 'panel.views.permission_denied_view'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
