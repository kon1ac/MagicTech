"""Панель: каталог и справочники (категории, бренды, характеристики, товары, акции)."""

from django.contrib import messages
from django.db import transaction
from django.db.models import ProtectedError, Q
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from panel.decorators import panel_login_required, permission_required
from panel.forms import (
    BrandForm,
    CategoryForm,
    CharacteristicForm,
    ProductForm,
    ProductImageForm,
    PromotionForm,
    ReturnReasonForm,
    UnitForm,
)
from panel.listing import apply_sorting, default_filter_redirect, list_context, paginate
from shop.models import (
    Brand,
    Category,
    Characteristic,
    OrderStatusRef,
    Product,
    ProductImage,
    Promotion,
    PromotionTypeRef,
    ReturnReason,
    Unit,
)
from shop.services import pricing
from shop.services.audit import object_history, write_audit
from shop.services.catalog import available_subquery, invalidate_catalog_cache


def _snapshot(obj, exclude=()):
    data = model_to_dict(obj, exclude=list(exclude))
    return {k: (str(v) if v is not None and not isinstance(v, (int, float, bool, str, dict, list)) else v)
            for k, v in data.items()}


def _crud_form(request, *, form_class, instance=None, title, object_type, back, template='panel/form.html',
               files=False, extra=None):
    form = form_class(request.POST or None, request.FILES or None if files else None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        before = _snapshot(instance) if instance is not None and instance.pk else None
        with transaction.atomic():
            obj = form.save()
            write_audit(user=request.panel_user, object_type=object_type, object_id=obj.pk,
                        action='update' if before else 'create', before=before,
                        after=_snapshot(obj), request=request)
        invalidate_catalog_cache()
        messages.success(request, 'Сохранено.')
        return redirect(back)
    context = {'form': form, 'title': title, 'back': back}
    if instance is not None and instance.pk:
        context['history'] = object_history(object_type, instance.pk)
    context.update(extra or {})
    return render(request, template, context)


def _crud_delete(request, obj, *, object_type, back, title):
    if request.method == 'POST' and request.POST.get('confirm'):
        snapshot, obj_pk = _snapshot(obj), obj.pk
        try:
            obj.delete()
        except ProtectedError:
            messages.error(request, 'Объект используется в других документах — удаление запрещено. '
                                    'Сделайте его неактивным.')
            return redirect(back)
        write_audit(user=request.panel_user, object_type=object_type, object_id=obj_pk,
                    action='delete', before=snapshot, request=request)
        invalidate_catalog_cache()
        messages.success(request, 'Удалено.')
        return redirect(back)
    return render(request, 'panel/confirm.html', {'title': title, 'object': str(obj), 'back': back,
                                                  'text': 'Удаление необратимо и будет записано в журнал аудита.'})


def _simple_list(request, model, template, search_fields, sort_map, default_sort, section):
    actor = request.panel_user
    if (resp := default_filter_redirect(request, actor, section)):
        return resp
    q = request.GET.get('q', '').strip()
    qs = model.objects.all()
    if q:
        flt = Q()
        for field in search_fields:
            flt |= Q(**{f'{field}__icontains': q})
        qs = qs.filter(flt)
    qs, keys = apply_sorting(request, qs, sort_map, default_sort)
    return render(request, template, {'page_obj': paginate(request, qs, actor), 'q': q,
                                      **list_context(request, actor, section, keys)})


# ---------------------------------------------------------------- категории

@panel_login_required
@permission_required('categories', 'view')
def category_list_view(request):
    return _simple_list(request, Category.objects.select_related('id_parent').model,
                        'panel/catalog/category_list.html', ['category_name', 'category_slug'],
                        {'name': 'category_name', 'level': 'category_level', 'id': 'id_category'},
                        'level,name', 'categories')


@panel_login_required
@permission_required('categories', 'create')
def category_create_view(request):
    return _crud_form(request, form_class=CategoryForm, title='Новая категория', object_type='category',
                      back='panel:category_list')


@panel_login_required
@permission_required('categories', 'update')
def category_edit_view(request, pk):
    obj = get_object_or_404(Category, pk=pk)
    return _crud_form(request, form_class=CategoryForm, instance=obj, title=f'Категория «{obj}»',
                      object_type='category', back='panel:category_list',
                      extra={'related': [('Товары категории', f'/panel/products/?category={obj.pk}')]})


@panel_login_required
@permission_required('categories', 'delete')
@require_http_methods(['GET', 'POST'])
def category_delete_view(request, pk):
    obj = get_object_or_404(Category, pk=pk)
    return _crud_delete(request, obj, object_type='category', back='panel:category_list', title='Удаление категории')


# ---------------------------------------------------------------- бренды

@panel_login_required
@permission_required('brands', 'view')
def brand_list_view(request):
    return _simple_list(request, Brand, 'panel/catalog/brand_list.html', ['brand_name', 'brand_slug'],
                        {'name': 'brand_name', 'id': 'id_brand', 'active': 'is_active'}, 'name', 'brands')


@panel_login_required
@permission_required('brands', 'create')
def brand_create_view(request):
    return _crud_form(request, form_class=BrandForm, title='Новый бренд', object_type='brand',
                      back='panel:brand_list', files=True)


@panel_login_required
@permission_required('brands', 'update')
def brand_edit_view(request, pk):
    obj = get_object_or_404(Brand, pk=pk)
    return _crud_form(request, form_class=BrandForm, instance=obj, title=f'Бренд «{obj}»', object_type='brand',
                      back='panel:brand_list', files=True,
                      extra={'related': [('Товары бренда', f'/panel/products/?brand={obj.pk}')]})


@panel_login_required
@permission_required('brands', 'delete')
@require_http_methods(['GET', 'POST'])
def brand_delete_view(request, pk):
    obj = get_object_or_404(Brand, pk=pk)
    return _crud_delete(request, obj, object_type='brand', back='panel:brand_list', title='Удаление бренда')


# ---------------------------------------------------------------- характеристики

@panel_login_required
@permission_required('characteristics', 'view')
def characteristic_list_view(request):
    return _simple_list(request, Characteristic, 'panel/catalog/characteristic_list.html',
                        ['char_code', 'char_name'], {'name': 'char_name', 'code': 'char_code', 'order': 'sort_order'},
                        'order,name', 'characteristics')


@panel_login_required
@permission_required('characteristics', 'create')
def characteristic_create_view(request):
    return _crud_form(request, form_class=CharacteristicForm, title='Новая характеристика',
                      object_type='characteristic', back='panel:characteristic_list')


@panel_login_required
@permission_required('characteristics', 'update')
def characteristic_edit_view(request, pk):
    obj = get_object_or_404(Characteristic, pk=pk)
    return _crud_form(request, form_class=CharacteristicForm, instance=obj, title=f'Характеристика «{obj}»',
                      object_type='characteristic', back='panel:characteristic_list')


@panel_login_required
@permission_required('characteristics', 'delete')
@require_http_methods(['GET', 'POST'])
def characteristic_delete_view(request, pk):
    obj = get_object_or_404(Characteristic, pk=pk)
    return _crud_delete(request, obj, object_type='characteristic', back='panel:characteristic_list',
                        title='Удаление характеристики')


# ---------------------------------------------------------------- справочники

@panel_login_required
@permission_required('references', 'view')
def references_view(request):
    unit_form = UnitForm(request.POST if request.POST.get('form') == 'unit' else None, prefix='unit')
    reason_form = ReturnReasonForm(request.POST if request.POST.get('form') == 'reason' else None, prefix='reason')
    if request.method == 'POST':
        from users.permissions import has_permission

        if not has_permission(request.panel_user.user_role, 'references', 'update'):
            messages.error(request, 'Недостаточно прав.')
            return redirect('panel:references')
        form = unit_form if request.POST.get('form') == 'unit' else reason_form
        if form.is_valid():
            obj = form.save()
            write_audit(user=request.panel_user, object_type='reference', object_id=obj.pk, action='create',
                        after=_snapshot(obj), request=request)
            messages.success(request, 'Запись справочника добавлена.')
            return redirect('panel:references')
    return render(request, 'panel/catalog/references.html', {
        'units': Unit.objects.order_by('unit_name'), 'reasons': ReturnReason.objects.order_by('reason_name'),
        'statuses': OrderStatusRef.objects.all(), 'promo_types': PromotionTypeRef.objects.all(),
        'unit_form': unit_form, 'reason_form': reason_form,
    })


# ---------------------------------------------------------------- товары

PRODUCT_SORT = {'sku': 'product_sku', 'name': 'product_name', 'brand': 'id_brand__brand_name',
                'category': 'id_category__category_name', 'price': 'price_now', 'stock': 'available',
                'rating': 'rating_avg', 'created': 'created_at', 'active': 'is_active'}


@panel_login_required
@permission_required('products', 'view')
def product_list_view(request):
    actor = request.panel_user
    if (resp := default_filter_redirect(request, actor, 'products')):
        return resp
    q = request.GET.get('q', '').strip()
    qs = Product.objects.select_related('id_brand', 'id_category').annotate(
        price_now=pricing.current_price_subquery(), available=available_subquery())
    if q:
        qs = qs.filter(Q(product_sku__icontains=q) | Q(product_name__icontains=q) | Q(product_ean__icontains=q))
    filters = {k: request.GET.get(k, '') for k in ('category', 'brand', 'active', 'stock')}
    if filters['category'].isdigit():
        qs = qs.filter(id_category__in=get_object_or_404(Category, pk=filters['category']).descendant_ids())
    if filters['brand'].isdigit():
        qs = qs.filter(id_brand=filters['brand'])
    if filters['active'] in ('1', '0'):
        qs = qs.filter(is_active=filters['active'] == '1')
    if filters['stock'] == 'out':
        qs = qs.filter(available__lte=0)
    elif filters['stock'] == 'low':
        qs = qs.filter(available__gt=0, available__lte=5)
    qs, keys = apply_sorting(request, qs, PRODUCT_SORT, '-created')
    return render(request, 'panel/catalog/product_list.html', {
        'page_obj': paginate(request, qs, actor), 'q': q, 'filters': filters,
        'categories': Category.objects.order_by('category_name'), 'brands': Brand.objects.order_by('brand_name'),
        **list_context(request, actor, 'products', keys),
    })


def _save_product(request, form, product=None):
    before = _snapshot(product, exclude=['product_images']) if product else None
    before_price = product.current_price if product else None
    with transaction.atomic():
        obj = form.save()
        new_price = form.cleaned_data.get('price')
        if new_price is not None and new_price != before_price:
            pricing.set_price(obj, new_price, actor=request.panel_user,
                              reason=form.cleaned_data.get('price_reason') or ('Создание товара' if not product else 'Правка цены'))
            write_audit(user=request.panel_user, object_type='price', object_id=obj.pk, action='change',
                        before={'price': before_price}, after={'price': new_price},
                        reason=form.cleaned_data.get('price_reason'), request=request)
        write_audit(user=request.panel_user, object_type='product', object_id=obj.pk,
                    action='update' if product else 'create', before=before,
                    after=_snapshot(obj, exclude=['product_images']), request=request)
    invalidate_catalog_cache()
    return obj


@panel_login_required
@permission_required('products', 'create')
def product_create_view(request):
    form = ProductForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = _save_product(request, form)
        messages.success(request, 'Товар создан. Добавьте фотографии.')
        return redirect('panel:product_edit', pk=obj.pk)
    return render(request, 'panel/catalog/product_form.html', {'form': form, 'title': 'Новый товар',
                                                               'characteristics': Characteristic.objects.all()})


@panel_login_required
@permission_required('products', 'update')
def product_edit_view(request, pk):
    product = get_object_or_404(Product.objects.select_related('id_brand', 'id_category'), pk=pk)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        _save_product(request, form, product)
        messages.success(request, 'Товар сохранён.')
        return redirect('panel:product_edit', pk=pk)
    return render(request, 'panel/catalog/product_form.html', {
        'form': form, 'title': f'{product.product_sku} — {product.product_name}', 'product': product,
        'image_form': ProductImageForm(), 'images': product.media.all(),
        'prices': product.prices.select_related('id_user').order_by('-valid_from')[:20],
        'stock': getattr(product.stock_records.first(), 'pk', None) and product.stock_records.first(),
        'movements': product.movements.select_related('id_user', 'id_order').order_by('-created_at')[:15],
        'history': object_history('product', product.pk),
        'characteristics': Characteristic.objects.all(),
    })


@panel_login_required
@permission_required('products', 'update')
@require_POST
def product_image_add_view(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductImageForm(request.POST, request.FILES)
    if form.is_valid():
        with transaction.atomic():
            if form.cleaned_data['is_main']:
                product.media.update(is_main=False)
            image = ProductImage.objects.create(
                id_product=product, media_file=form.cleaned_data['media_file'],
                media_url=form.cleaned_data['media_url'] or None, media_alt=form.cleaned_data['media_alt'] or None,
                is_main=form.cleaned_data['is_main'] or not product.media.exists(),
                sort_order=product.media.count())
            write_audit(user=request.panel_user, object_type='product', object_id=pk, action='image_add',
                        after={'image': image.url}, request=request)
        messages.success(request, 'Изображение добавлено.')
    else:
        messages.error(request, '; '.join(e for errs in form.errors.values() for e in errs))
    return redirect('panel:product_edit', pk=pk)


@panel_login_required
@permission_required('products', 'update')
@require_POST
def product_image_delete_view(request, pk, image_id):
    image = get_object_or_404(ProductImage, pk=image_id, id_product_id=pk)
    write_audit(user=request.panel_user, object_type='product', object_id=pk, action='image_delete',
                before={'image': image.url}, request=request)
    image.delete()
    messages.success(request, 'Изображение удалено.')
    return redirect('panel:product_edit', pk=pk)


@panel_login_required
@permission_required('products', 'delete')
@require_http_methods(['GET', 'POST'])
def product_delete_view(request, pk):
    obj = get_object_or_404(Product, pk=pk)
    return _crud_delete(request, obj, object_type='product', back='panel:product_list', title='Удаление товара')


@panel_login_required
@permission_required('products', 'update')
@require_POST
def product_bulk_view(request):
    from users.permissions import has_permission

    ids = [int(i) for i in request.POST.getlist('ids') if i.isdigit()]
    action = request.POST.get('action')
    back = request.META.get('HTTP_REFERER') or '/panel/products/'
    if not ids:
        messages.error(request, 'Не выбраны товары.')
        return redirect(back)
    if not request.POST.get('confirm'):
        messages.error(request, 'Подтвердите массовую операцию.')
        return redirect(back)
    with transaction.atomic():
        if action in ('activate', 'archive'):
            Product.objects.filter(pk__in=ids).update(is_active=action == 'activate')
        elif action == 'delete':
            if not has_permission(request.panel_user.user_role, 'products', 'delete'):
                messages.error(request, 'Удаление доступно только администратору.')
                return redirect(back)
            try:
                Product.objects.filter(pk__in=ids).delete()
            except ProtectedError:
                transaction.set_rollback(True)
                messages.error(request, 'Часть товаров есть в заказах — удалить нельзя. Используйте архивацию.')
                return redirect(back)
        else:
            messages.error(request, 'Неизвестная операция.')
            return redirect(back)
        for pk in ids:
            write_audit(user=request.panel_user, object_type='product', object_id=pk, action=f'bulk_{action}',
                        reason='Массовая операция', request=request)
    invalidate_catalog_cache()
    messages.success(request, f'Операция выполнена для {len(ids)} товаров.')
    return redirect(back)


# ---------------------------------------------------------------- акции

@panel_login_required
@permission_required('promotions', 'view')
def promotion_list_view(request):
    return _simple_list(request, Promotion, 'panel/promotions/list.html',
                        ['promotion_name', 'promotion_promo_code'],
                        {'name': 'promotion_name', 'start': 'start_at', 'end': 'end_at', 'value': 'promotion_value',
                         'active': 'is_active', 'used': 'usage_count'}, '-start', 'promotions')


@panel_login_required
@permission_required('promotions', 'create')
def promotion_create_view(request):
    form = PromotionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            promo = form.save(commit=False)
            promo.id_user = request.panel_user
            promo.save()
            form.instance = promo
            form.save()
            write_audit(user=request.panel_user, object_type='promotion', object_id=promo.pk, action='create',
                        after=_snapshot(promo), request=request)
        messages.success(request, 'Акция создана.')
        return redirect('panel:promotion_list')
    return render(request, 'panel/form.html', {'form': form, 'title': 'Новая акция', 'back': 'panel:promotion_list'})


@panel_login_required
@permission_required('promotions', 'update')
def promotion_edit_view(request, pk):
    obj = get_object_or_404(Promotion, pk=pk)
    return _crud_form(request, form_class=PromotionForm, instance=obj, title=f'Акция «{obj}»',
                      object_type='promotion', back='panel:promotion_list')


@panel_login_required
@permission_required('promotions', 'delete')
@require_http_methods(['GET', 'POST'])
def promotion_delete_view(request, pk):
    obj = get_object_or_404(Promotion, pk=pk)
    return _crud_delete(request, obj, object_type='promotion', back='panel:promotion_list', title='Удаление акции')
