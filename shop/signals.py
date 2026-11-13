"""Инвалидация кеша каталога при изменениях справочников (в т.ч. из shell)."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from shop.models import Brand, Category, Characteristic, Product


def _bust_catalog(**_kwargs):
    from shop.services.catalog import invalidate_catalog_cache
    invalidate_catalog_cache()


for model in (Category, Brand, Characteristic, Product):
    receiver(post_save, sender=model)(_bust_catalog)
    receiver(post_delete, sender=model)(_bust_catalog)
