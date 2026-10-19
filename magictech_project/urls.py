<<<<<<< HEAD
"""Маршруты MagicTech: витрина (/), панель (/panel/), API (/api/), техническая админка (/admin/)."""

=======
"""
URL configuration for magictech_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
<<<<<<< HEAD
=======
from django.views.generic import RedirectView
>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719

admin.site.site_header = 'MagicTech — техническая админка Django'
admin.site.site_title = 'MagicTech Admin'
admin.site.index_title = 'Модели и миграции'

urlpatterns = [
<<<<<<< HEAD
    path('panel/', include('panel.urls')),
    path('api/', include('api.urls')),
    path('admin/', admin.site.urls),
    path('', include('store.urls')),
]

handler403 = 'panel.views.permission_denied_view'

=======
    path('', RedirectView.as_view(url='/panel/', permanent=False), name='home'),
    path('panel/', include('panel.urls')),
    path('admin/', admin.site.urls),
]

>>>>>>> b935e5dc6d02be0bbd35e6ef434b9d4cc58e4719
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
