from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    verbose_name = 'REST API'

    def ready(self):
        from api import schema  # noqa: F401 — регистрация схемы авторизации в OpenAPI
