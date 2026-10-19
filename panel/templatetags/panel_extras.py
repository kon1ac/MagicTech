from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return key
    return mapping.get(key, key)
