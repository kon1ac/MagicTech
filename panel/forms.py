import json

from django import forms
from django.core.exceptions import ValidationError

from shop.models import (
    Brand,
    Category,
    Characteristic,
    Product,
    Promotion,
    ReturnReason,
    Unit,
)
from users.constants import API_SCOPES, ROLE_CHOICES, ROLE_CUSTOMER, STAFF_ROLES
from users.models import AuthCredentials, UserProfiles, UserSettings


class LoginForm(forms.Form):
    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autocomplete': 'username'}))
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )


def validate_password_strength(value: str) -> None:
    if len(value) < 8:
        raise ValidationError('Пароль — не короче 8 символов.')
    if value.isdigit() or value.isalpha():
        raise ValidationError('Пароль должен содержать буквы и цифры.')


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label='Пароль',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Для нового пользователя обязателен; при редактировании — оставьте пустым, чтобы не менять.',
    )
    profile_first_name = forms.CharField(label='Имя', required=False, max_length=100)
    profile_last_name = forms.CharField(label='Фамилия', required=False, max_length=100)
    profile_phone = forms.CharField(label='Телефон', required=False, max_length=30)

    class Meta:
        model = AuthCredentials
        fields = ('email', 'user_role', 'is_active')
        labels = {'email': 'Email', 'user_role': 'Роль', 'is_active': 'Активен'}

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields['user_role'] = forms.ChoiceField(label='Роль', choices=ROLE_CHOICES)
        if self.instance.pk:
            self.fields['user_role'].initial = self.instance.user_role
            profile = getattr(self.instance, 'profile', None)
            if profile:
                self.fields['profile_first_name'].initial = profile.profile_first_name
                self.fields['profile_last_name'].initial = profile.profile_last_name
                self.fields['profile_phone'].initial = profile.profile_phone

    def clean_user_role(self):
        role = self.cleaned_data['user_role']
        if role not in STAFF_ROLES and role != ROLE_CUSTOMER:
            raise ValidationError('Неизвестная роль.')
        if self.actor and self.instance.pk == self.actor.pk and role != self.actor.user_role:
            raise ValidationError('Нельзя сменить роль самому себе.')
        return role

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not self.instance.pk and not password:
            raise ValidationError('Задайте пароль для нового пользователя.')
        if password:
            validate_password_strength(password)
        return password

    def clean_is_active(self):
        active = self.cleaned_data.get('is_active')
        if self.actor and self.instance.pk == self.actor.pk and not active:
            raise ValidationError('Нельзя деактивировать собственную учётную запись.')
        return active

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
            profile, _ = UserProfiles.objects.get_or_create(id_user=user)
            profile.profile_first_name = self.cleaned_data.get('profile_first_name') or None
            profile.profile_last_name = self.cleaned_data.get('profile_last_name') or None
            profile.profile_phone = self.cleaned_data.get('profile_phone') or None
            profile.save()
        return user


class JSONDictField(forms.CharField):
    """JSON-объект в textarea с понятной ошибкой валидации."""

    widget = forms.Textarea(attrs={'rows': 4, 'class': 'mono'})

    def prepare_value(self, value):
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=1)
        return value

    def to_python(self, value):
        value = super().to_python(value)
        if not value:
            return {}
        try:
            data = json.loads(value)
        except ValueError as exc:
            raise ValidationError(f'Некорректный JSON: {exc}') from exc
        if not isinstance(data, dict):
            raise ValidationError('Ожидается JSON-объект {"ключ": "значение"}.')
        return data


class CategoryForm(forms.ModelForm):
    category_attributes = JSONDictField(
        label='Атрибуты фильтрации', required=False,
        help_text='Например: {"filters": ["connection", "color"]}')

    class Meta:
        model = Category
        fields = ('category_name', 'category_slug', 'id_parent', 'category_attributes', 'is_active')
        labels = {'category_name': 'Название', 'category_slug': 'Slug (URL)', 'id_parent': 'Родительская категория',
                  'is_active': 'Активна'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Category.objects.filter(category_level__lt=3).order_by('category_level', 'category_name')
        if self.instance.pk:
            qs = qs.exclude(pk__in=self.instance.descendant_ids())
        self.fields['id_parent'].queryset = qs
        self.fields['category_slug'].required = True

    def clean(self):
        data = super().clean()
        parent = data.get('id_parent')
        level = (parent.category_level + 1) if parent else 1
        if level > 3:
            raise ValidationError('Допускается не более 3 уровней вложенности.')
        self.instance.category_level = level
        return data


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ('brand_name', 'brand_slug', 'brand_description', 'brand_logo_url', 'is_active')
        labels = {'brand_name': 'Название', 'brand_slug': 'Slug', 'brand_description': 'Описание',
                  'brand_logo_url': 'Логотип', 'is_active': 'Активен'}


class CharacteristicForm(forms.ModelForm):
    class Meta:
        model = Characteristic
        fields = ('char_code', 'char_name', 'char_value_type', 'id_unit', 'is_filterable', 'sort_order')
        labels = {'char_code': 'Код (латиница)', 'char_name': 'Название', 'char_value_type': 'Тип значения',
                  'id_unit': 'Единица измерения', 'is_filterable': 'Показывать в фильтрах каталога',
                  'sort_order': 'Порядок'}


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ('unit_code', 'unit_name')
        labels = {'unit_code': 'Код', 'unit_name': 'Название'}


class ReturnReasonForm(forms.ModelForm):
    class Meta:
        model = ReturnReason
        fields = ('reason_code', 'reason_name', 'is_defect')
        labels = {'reason_code': 'Код', 'reason_name': 'Причина', 'is_defect': 'Брак (товар списывается)'}


class ProductForm(forms.ModelForm):
    product_characteristics = JSONDictField(
        label='Характеристики', required=False,
        help_text='JSON: {"connection": "USB", "color": "Чёрный", "backlight": "RGB"}')
    price = forms.DecimalField(label='Цена, ₽', min_value=0, decimal_places=2, max_digits=12, required=False)
    price_reason = forms.CharField(label='Причина изменения цены', required=False, max_length=255)

    class Meta:
        model = Product
        fields = (
            'product_sku', 'product_ean', 'product_name', 'id_brand', 'id_category', 'id_unit',
            'product_description', 'product_characteristics', 'cost_price',
            'seo_title', 'seo_description', 'seo_keywords', 'is_active',
        )
        labels = {
            'product_sku': 'Артикул (SKU)', 'product_ean': 'EAN / штрихкод', 'product_name': 'Название',
            'id_brand': 'Бренд', 'id_category': 'Категория', 'id_unit': 'Единица измерения',
            'product_description': 'Описание', 'cost_price': 'Себестоимость, ₽',
            'seo_title': 'SEO title', 'seo_description': 'SEO description', 'seo_keywords': 'SEO keywords',
            'is_active': 'Продаётся',
        }
        widgets = {'product_description': forms.Textarea(attrs={'rows': 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product_name'].widget.attrs['data-hotkey'] = 'ctrl+e'
        if self.instance.pk:
            self.fields['price'].initial = self.instance.current_price
        else:
            self.fields['price'].required = True

    def clean_product_ean(self):
        ean = self.cleaned_data.get('product_ean') or None
        if ean and (not ean.isdigit() or len(ean) not in (8, 12, 13, 14)):
            raise ValidationError('EAN — 8, 12, 13 или 14 цифр.')
        return ean

    def clean_product_characteristics(self):
        data = self.cleaned_data.get('product_characteristics') or {}
        known = set(Characteristic.objects.values_list('char_code', flat=True))
        unknown = [k for k in data if known and k not in known]
        if unknown:
            raise ValidationError(f'Неизвестные характеристики: {", ".join(unknown)}. Добавьте их в справочник.')
        return data


class ProductImageForm(forms.Form):
    media_file = forms.ImageField(label='Файл изображения', required=False)
    media_url = forms.URLField(label='или URL изображения', required=False)
    media_alt = forms.CharField(label='Alt-текст', required=False, max_length=255)
    is_main = forms.BooleanField(label='Главное фото', required=False)

    def clean(self):
        data = super().clean()
        if not data.get('media_file') and not data.get('media_url'):
            raise ValidationError('Загрузите файл или укажите URL.')
        return data


class PromotionForm(forms.ModelForm):
    products = forms.ModelMultipleChoiceField(
        label='Товары', queryset=Product.objects.filter(is_active=True).order_by('product_sku'), required=False,
        widget=forms.SelectMultiple(attrs={'size': 6}))
    categories = forms.ModelMultipleChoiceField(
        label='Категории', queryset=Category.objects.order_by('category_name'), required=False,
        widget=forms.SelectMultiple(attrs={'size': 6}))
    brands = forms.ModelMultipleChoiceField(
        label='Бренды', queryset=Brand.objects.order_by('brand_name'), required=False,
        widget=forms.SelectMultiple(attrs={'size': 6}))

    class Meta:
        model = Promotion
        fields = (
            'promotion_name', 'promotion_type', 'promotion_value', 'promotion_promo_code',
            'promotion_description', 'start_at', 'end_at', 'promotion_min_sum', 'promotion_min_qty',
            'usage_limit', 'is_stackable', 'is_active',
        )
        labels = {
            'promotion_name': 'Название', 'promotion_type': 'Тип', 'promotion_value': 'Размер скидки',
            'promotion_promo_code': 'Промокод (пусто — автоматическая акция)', 'promotion_description': 'Описание',
            'start_at': 'Начало', 'end_at': 'Окончание', 'promotion_min_sum': 'Мин. сумма, ₽',
            'promotion_min_qty': 'Мин. количество, шт.', 'usage_limit': 'Лимит использований промокода',
            'is_stackable': 'Суммируется с другими акциями', 'is_active': 'Активна',
        }
        widgets = {
            'start_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'end_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'promotion_description': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['promotion_type'] = forms.ChoiceField(
            label='Тип', choices=[('percent', 'Процент'), ('fixed', 'Фиксированная сумма, ₽')])
        if self.instance.pk:
            self.fields['products'].initial = [l.id_product_id for l in self.instance.promotion_products.all()]
            self.fields['categories'].initial = [l.id_category_id for l in self.instance.promotion_categories.all()]
            self.fields['brands'].initial = [l.id_brand_id for l in self.instance.promotion_brands.all()]

    def clean_promotion_promo_code(self):
        code = (self.cleaned_data.get('promotion_promo_code') or '').strip().upper()
        return code or None

    def clean(self):
        data = super().clean()
        start, end = data.get('start_at'), data.get('end_at')
        if start and end and end <= start:
            raise ValidationError('Окончание акции должно быть позже начала.')
        value = data.get('promotion_value')
        if value is not None:
            if value <= 0:
                raise ValidationError('Размер скидки должен быть положительным.')
            if data.get('promotion_type') == 'percent' and value > 100:
                raise ValidationError('Процент скидки — не больше 100.')
        return data

    def save(self, commit=True):
        from shop.models import PromotionBrand, PromotionCategory, PromotionProduct

        promo = super().save(commit=commit)
        if commit:
            promo.promotion_products.all().delete()
            promo.promotion_categories.all().delete()
            promo.promotion_brands.all().delete()
            PromotionProduct.objects.bulk_create(
                [PromotionProduct(id_promotion=promo, id_product=p) for p in self.cleaned_data['products']])
            PromotionCategory.objects.bulk_create(
                [PromotionCategory(id_promotion=promo, id_category=c) for c in self.cleaned_data['categories']])
            PromotionBrand.objects.bulk_create(
                [PromotionBrand(id_promotion=promo, id_brand=b) for b in self.cleaned_data['brands']])
        return promo


class StockAdjustForm(forms.Form):
    delta = forms.IntegerField(label='Изменение (+/-)')
    reason = forms.CharField(label='Причина корректировки', widget=forms.Textarea(attrs={'rows': 2}))
    confirm = forms.BooleanField(
        label='Подтверждаю критическую операцию корректировки остатка',
        required=True,
    )

    def clean_delta(self):
        delta = self.cleaned_data['delta']
        if delta == 0:
            raise ValidationError('Изменение не может быть нулевым.')
        return delta


class StockReceiptForm(forms.Form):
    product = forms.ModelChoiceField(label='Товар', queryset=Product.objects.order_by('product_sku'))
    quantity = forms.IntegerField(label='Фактически принято, шт.', min_value=1)
    expected_quantity = forms.IntegerField(label='По накладной (учётное), шт.', min_value=0, required=False)
    document_number = forms.CharField(label='Номер приходной накладной', max_length=50)
    reason = forms.CharField(label='Комментарий', required=False)


class OrderStatusForm(forms.Form):
    new_status = forms.ChoiceField(label='Новый статус')
    reason = forms.CharField(label='Комментарий / причина', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    confirm_cancel = forms.BooleanField(
        label='Подтверждаю отмену заказа (критическая операция)',
        required=False,
    )

    def __init__(self, *args, allowed: set, **kwargs):
        super().__init__(*args, **kwargs)
        from users.constants import ORDER_STATUS_LABELS

        order = list(ORDER_STATUS_LABELS)
        self.fields['new_status'].choices = [
            (code, ORDER_STATUS_LABELS.get(code, code)) for code in sorted(allowed, key=order.index)
        ]

    def clean(self):
        data = super().clean()
        if data.get('new_status') == 'CANCELLED':
            if not data.get('confirm_cancel'):
                raise ValidationError('Подтвердите критическую операцию отмены.')
            if not (data.get('reason') or '').strip():
                raise ValidationError('Укажите причину отмены.')
        return data


class BulkStatusForm(forms.Form):
    ids = forms.CharField(widget=forms.HiddenInput)
    new_status = forms.ChoiceField(label='Новый статус')
    reason = forms.CharField(label='Причина', required=False)
    confirm = forms.BooleanField(label='Подтверждаю массовую операцию', required=True)


class ReviewModerationForm(forms.Form):
    review_status = forms.ChoiceField(
        label='Статус', choices=[('pending', 'На модерации'), ('approved', 'Опубликовать'), ('rejected', 'Отклонить')])
    seller_answer = forms.CharField(label='Ответ продавца', required=False, widget=forms.Textarea(attrs={'rows': 3}))


class RefundForm(forms.Form):
    amount = forms.DecimalField(label='Сумма возврата, ₽', min_value=0.01, decimal_places=2, max_digits=12)
    reason = forms.CharField(label='Причина')
    confirm = forms.BooleanField(label='Подтверждаю возврат денежных средств', required=True)


class ManualConfirmForm(forms.Form):
    reason = forms.CharField(label='Основание (номер выписки, реестра эквайринга)')
    confirm = forms.BooleanField(label='Подтверждаю поступление денег', required=True)


class ReturnStatusForm(forms.Form):
    new_status = forms.ChoiceField(label='Новый статус')
    decision = forms.CharField(label='Решение / комментарий', required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, allowed: set, **kwargs):
        super().__init__(*args, **kwargs)
        from users.constants import RETURN_STATUS_LABELS

        self.fields['new_status'].choices = [(c, RETURN_STATUS_LABELS[c]) for c in RETURN_STATUS_LABELS if c in allowed]


class ReturnAuditEditForm(forms.Form):
    refund_amount = forms.DecimalField(label='Сумма к возврату, ₽', min_value=0, decimal_places=2, max_digits=12)
    return_description = forms.CharField(label='Описание', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    reason = forms.CharField(label='Причина правки (обязательна для утверждённой заявки)', required=False)


class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = UserSettings
        fields = ('theme', 'language', 'date_format', 'currency_format', 'page_size', 'hotkeys_enabled')
        labels = {'theme': 'Тема', 'language': 'Язык интерфейса', 'date_format': 'Формат даты',
                  'currency_format': 'Формат валюты', 'page_size': 'Строк на странице',
                  'hotkeys_enabled': 'Горячие клавиши включены'}


class ImportUploadForm(forms.Form):
    KINDS = [('products', 'Товары'), ('stock', 'Остатки'), ('prices', 'Цены')]
    kind = forms.ChoiceField(label='Что импортируем', choices=KINDS)
    file = forms.FileField(label='Файл CSV (UTF-8 / Windows-1251, разделитель ; или ,) или XLSX')

    def clean_file(self):
        f = self.cleaned_data['file']
        if f.size > 30 * 1024 * 1024:
            raise ValidationError('Файл больше 30 МБ.')
        if not f.name.lower().endswith(('.csv', '.txt', '.xlsx')):
            raise ValidationError('Допустимы файлы .csv или .xlsx.')
        return f


class StatementUploadForm(forms.Form):
    source = forms.ChoiceField(label='Источник', choices=[('bank', 'Банковская выписка'), ('acquiring', 'Реестр эквайринга')])
    file = forms.FileField(label='Файл CSV или XLSX (номер заказа/назначение, сумма, дата)')


class ApiTokenForm(forms.Form):
    name = forms.CharField(label='Название (система-потребитель)', max_length=100)
    user = forms.ModelChoiceField(label='Сервисная учётная запись', queryset=AuthCredentials.objects.filter(is_active=True).order_by('email'))
    scopes = forms.MultipleChoiceField(label='Области доступа', choices=list(API_SCOPES.items()),
                                       widget=forms.CheckboxSelectMultiple)
    expires_days = forms.IntegerField(label='Срок действия, дней (пусто — бессрочно)', required=False, min_value=1, max_value=730)


class ArchiveGrantForm(forms.Form):
    user = forms.ModelChoiceField(label='Пользователь', queryset=AuthCredentials.objects.exclude(user_role=ROLE_CUSTOMER).order_by('email'))
    days = forms.IntegerField(label='На сколько дней', min_value=1, max_value=90, initial=7)
    reason = forms.CharField(label='Основание (запрос, служебная записка)')


class RestoreForm(forms.Form):
    confirm_name = forms.CharField(label='Введите имя базы данных для подтверждения')
    confirm = forms.BooleanField(label='Понимаю, что текущие данные будут заменены данными из копии', required=True)
