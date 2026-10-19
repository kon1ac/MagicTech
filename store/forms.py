from django import forms
from django.core.exceptions import ValidationError

from panel.forms import validate_password_strength
from users.constants import PAYMENT_METHOD_LABELS, STORE_PAYMENT_METHODS
from users.models import AuthCredentials


class RegisterForm(forms.Form):
    email = forms.EmailField(label='Email')
    first_name = forms.CharField(label='Имя', max_length=100)
    phone = forms.CharField(label='Телефон', max_length=30, required=False)
    password = forms.CharField(label='Пароль', widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    password2 = forms.CharField(label='Повторите пароль', widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if AuthCredentials.objects.filter(email__iexact=email).exists():
            raise ValidationError('Пользователь с таким email уже зарегистрирован.')
        return email

    def clean_password(self):
        password = self.cleaned_data['password']
        validate_password_strength(password)
        return password

    def clean(self):
        data = super().clean()
        if data.get('password') and data.get('password') != data.get('password2'):
            raise ValidationError('Пароли не совпадают.')
        return data


class LoginForm(forms.Form):
    email = forms.EmailField(label='Email')
    password = forms.CharField(label='Пароль', widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}))


class CheckoutForm(forms.Form):
    payment_method = forms.ChoiceField(label='Способ оплаты', choices=[(m, PAYMENT_METHOD_LABELS[m]) for m in STORE_PAYMENT_METHODS],
                                       widget=forms.RadioSelect, initial='card_online')
    delivery_address = forms.CharField(label='Адрес доставки', widget=forms.Textarea(attrs={'rows': 2}), max_length=500)
    contact_phone = forms.CharField(label='Телефон для связи', max_length=30)
    comment = forms.CharField(label='Комментарий к заказу', required=False, widget=forms.Textarea(attrs={'rows': 2}),
                              max_length=1000)
    offer_accepted = forms.BooleanField(label='Я согласен с условиями публичной оферты', required=True)

    def clean_contact_phone(self):
        phone = self.cleaned_data['contact_phone']
        digits = ''.join(ch for ch in phone if ch.isdigit())
        if len(digits) < 10:
            raise ValidationError('Укажите телефон полностью.')
        return phone


class ProfileForm(forms.Form):
    first_name = forms.CharField(label='Имя', max_length=100, required=False)
    last_name = forms.CharField(label='Фамилия', max_length=100, required=False)
    phone = forms.CharField(label='Телефон', max_length=30, required=False)
    address = forms.CharField(label='Адрес доставки по умолчанию', required=False, widget=forms.Textarea(attrs={'rows': 2}))


class ReviewForm(forms.Form):
    rating = forms.TypedChoiceField(label='Оценка', coerce=int, choices=[(i, '★' * i) for i in range(5, 0, -1)])
    text = forms.CharField(label='Отзыв', widget=forms.Textarea(attrs={'rows': 3}), max_length=5000)
    photo = forms.ImageField(label='Фото (необязательно)', required=False)


class QuestionForm(forms.Form):
    text = forms.CharField(label='Вопрос о товаре', widget=forms.Textarea(attrs={'rows': 2}), max_length=2000)
