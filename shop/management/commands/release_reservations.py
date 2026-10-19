from django.core.management.base import BaseCommand

from shop.services import orders


class Command(BaseCommand):
    help = 'Снимает просроченные резервы корзин и отменяет неоплаченные онлайн-заказы (для cron)'

    def handle(self, *args, **options):
        carts = orders.release_expired_cart_reservations()
        expired = orders.expire_unpaid_orders()
        self.stdout.write(f'Снято резервов корзин: {carts}; отменено неоплаченных заказов: {expired}')
