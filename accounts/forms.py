from django import forms
from django.contrib.auth import authenticate

from accounts.models import User
from accounts.phone import InvalidPhoneError, normalize_phone


class PhoneField(forms.CharField):
    """A phone number normalised to ``+998XXXXXXXXX``."""

    def __init__(self, **kwargs):
        kwargs.setdefault("label", "Telefon raqami")
        kwargs.setdefault("max_length", 32)
        kwargs.setdefault("widget", forms.TextInput(attrs={
            "type": "tel", "placeholder": "+998 90 123 45 67", "autocomplete": "tel",
        }))
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)
        try:
            return normalize_phone(value)
        except InvalidPhoneError as error:
            raise forms.ValidationError(str(error))


class NewPhoneField(PhoneField):
    """A phone number that no existing account uses yet."""

    def clean(self, value):
        phone = super().clean(value)
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("Bu telefon raqami allaqachon ro'yxatdan o'tgan. Kirish sahifasidan foydalaning.")
        return phone


class SignupForm(forms.Form):
    """Client ("Mijoz") sign-up: name and phone number, no password."""

    first_name = forms.CharField(label="Ism", max_length=150)
    last_name = forms.CharField(label="Familiya", max_length=150)
    phone = NewPhoneField()

    def save(self) -> User:
        user = User(
            first_name=self.cleaned_data["first_name"].strip(),
            last_name=self.cleaned_data["last_name"].strip(),
            phone=self.cleaned_data["phone"],
            role=User.Role.USER,
        )
        user.set_unusable_password()
        user.save()
        return user


class LoginForm(forms.Form):
    phone = forms.CharField(
        label="Telefon raqami", max_length=32,
        widget=forms.TextInput(attrs={"type": "tel", "placeholder": "+998 90 123 45 67", "autocomplete": "tel"}),
    )

    def clean(self):
        cleaned = super().clean()
        raw = (cleaned.get("phone") or "").strip()
        if not raw:
            return cleaned
        # Accounts created before phone numbers were normalised may hold the
        # number exactly as the person typed it, so try that as well.
        candidates = []
        try:
            candidates.append(normalize_phone(raw))
        except InvalidPhoneError:
            pass
        candidates.append(raw)
        for phone in candidates:
            user = authenticate(phone=phone)
            if user is not None:
                cleaned["user"] = user
                return cleaned
        raise forms.ValidationError("Bu telefon raqami bilan hisob topilmadi.")
