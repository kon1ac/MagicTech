from django import forms
from django.core.exceptions import ValidationError

from shop.models import Brand, Category, Product, Promotion, Review
from users.constants import ROLE_CHOICES, ROLE_CUSTOMER, STAFF_ROLES
from users.models import AuthCredentials, UserProfiles


class LoginForm(forms.Form):
    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autocomplete': 'username'}))
    password = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label='Пароль',
        required=False,
        widget=forms.PasswordInput,
        help_text='Оставьте пустым, чтобы не менять пароль.',
    )
    profile_first_name = forms.CharField(label='Имя', required=False)
    profile_last_name = forms.CharField(label='Фамилия', required=False)
    profile_phone = forms.CharField(label='Телефон', required=False)

    class Meta:
        model = AuthCredentials
        fields = ('email', 'user_role', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user_role'].choices = ROLE_CHOICES
        if self.instance.pk:
            profile = getattr(self.instance, 'profile', None)
            if profile:
                self.fields['profile_first_name'].initial = profile.profile_first_name
                self.fields['profile_last_name'].initial = profile.profile_last_name
                self.fields['profile_phone'].initial = profile.profile_phone

    def clean_user_role(self):
        role = self.cleaned_data['user_role']
        if role not in STAFF_ROLES and role != ROLE_CUSTOMER:
            raise ValidationError('Неизвестная роль.')
        return role

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        elif not user.pk:
            user.set_password('ChangeMe123!')
        if commit:
            user.save()
            profile, _ = UserProfiles.objects.get_or_create(id_user=user)
            profile.profile_first_name = self.cleaned_data.get('profile_first_name') or profile.profile_first_name
            profile.profile_last_name = self.cleaned_data.get('profile_last_name') or profile.profile_last_name
            profile.profile_phone = self.cleaned_data.get('profile_phone') or profile.profile_phone
            profile.save()
        return user


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = (
            'category_name',
            'category_slug',
            'id_parent',
            'category_level',
            'category_attributes',
            'is_active',
        )
        widgets = {
            'category_attributes': forms.Textarea(attrs={'rows': 3}),
        }


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ('brand_name', 'brand_slug', 'brand_description', 'brand_logo_url', 'is_active')


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            'product_sku',
            'product_ean',
            'product_name',
            'id_brand',
            'id_category',
            'product_description',
            'product_characteristics',
            'is_active',
        )
        widgets = {
            'product_description': forms.Textarea(attrs={'rows': 4}),
            'product_characteristics': forms.Textarea(attrs={'rows': 4}),
        }


class PromotionForm(forms.ModelForm):
    class Meta:
        model = Promotion
        fields = (
            'promotion_name',
            'promotion_type',
            'promotion_value',
            'promotion_promo_code',
            'start_at',
            'end_at',
            'is_active',
        )
        widgets = {
            'start_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class StockAdjustForm(forms.Form):
    delta = forms.IntegerField(label='Изменение (+/-)')
    reason = forms.CharField(label='Причина корректировки', widget=forms.Textarea(attrs={'rows': 2}))
    confirm = forms.BooleanField(
        label='Подтверждаю критическую операцию корректировки остатка',
        required=True,
    )


class OrderStatusForm(forms.Form):
    new_status = forms.ChoiceField(label='Новый статус')
    reason = forms.CharField(label='Комментарий', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    confirm_cancel = forms.BooleanField(
        label='Подтверждаю отмену заказа (критическая операция)',
        required=False,
    )

    def __init__(self, *args, current_status: str, **kwargs):
        super().__init__(*args, **kwargs)
        from users.constants import ORDER_STATUS_FLOW, ORDER_STATUS_LABELS

        choices = [
            (code, ORDER_STATUS_LABELS.get(code, code))
            for code in sorted(ORDER_STATUS_FLOW.get(current_status, set()))
        ]
        self.fields['new_status'].choices = choices


class ReviewModerationForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ('review_status',)
