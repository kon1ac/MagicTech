from django.apps import AppConfig


class ShopConfig(AppConfig):
    name = 'shop'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from shop import signals  # noqa: F401
