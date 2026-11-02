from django.db.models import Sum

from users.auth_session import get_current_user


def store_context(request):
    if not request.path.startswith(('/panel', '/admin', '/api')):
        from shop.services.catalog import category_tree

        user = get_current_user(request)
        cart_count = 0
        if request.session.session_key or user:
            from shop.services.cart import get_cart

            cart = get_cart(user=user, session_key=None if user else request.session.session_key, create=False)
            if cart:
                cart_count = cart.items.aggregate(Sum('cart_item_quantity'))['cart_item_quantity__sum'] or 0
        # дерево категорий нужно мега-меню в шапке; сервис отдаёт кешированный справочник
        return {'store_user': user, 'cart_count': cart_count, 'nav_tree': category_tree()}
    return {}
