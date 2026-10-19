from users.auth_session import get_current_user


def store_context(request):
    if not request.path.startswith(('/panel', '/admin', '/api')):
        user = get_current_user(request)
        cart_count = 0
        if request.session.session_key or user:
            from shop.services.cart import get_cart

            cart = get_cart(user=user, session_key=request.session.session_key, create=False)
            if cart:
                cart_count = sum(cart.items.values_list('cart_item_quantity', flat=True))
        return {'store_user': user, 'cart_count': cart_count}
    return {}
