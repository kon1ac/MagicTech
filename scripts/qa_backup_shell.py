import django
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'magictech_project.settings')
django.setup()

from django.apps import apps
from django.contrib.auth import get_user_model
from shop.services import dbadmin

User = get_user_model()
u = User.objects.get(email='db@magtech.local')
print('user', u.pk, getattr(u, 'user_role', None))

from orders.models import Order
for oid in (99, 47, 101):
    o = Order.objects.filter(pk=oid).first()
    if o:
        print('order', oid, o.order_number, o.order_status)

try:
    rec = dbadmin.create_backup('full', actor=u, request=None)
    print('backup', rec.pk, rec.backup_status, rec.file_path)
    print('out', (rec.backup_output or '')[-600:])
except Exception as e:
    print('EXC', type(e).__name__, e)

for m in apps.get_models():
    if 'backup' in m.__name__.lower():
        print('model', m.__name__, m.objects.count())
        for row in m.objects.order_by('-pk')[:8]:
            print(
                ' ',
                row.pk,
                getattr(row, 'backup_status', None),
                getattr(row, 'file_path', None),
                getattr(row, 'backup_kind', None),
            )
