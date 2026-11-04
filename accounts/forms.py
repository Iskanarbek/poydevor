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


class SetPasswordForm(forms.Form):
    """Create (or change) an architect's password. No strength rules: anything goes."""

    password = forms.CharField(
        label="Yangi parol", min_length=1, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="Parolni takrorlang", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password") != cleaned.get("password_confirm"):
            self.add_error("password_confirm", "Parollar bir xil emas.")
        return cleaned


class LoginForm(forms.Form):
    phone = forms.CharField(
        label="Telefon raqami", max_length=32,
        widget=forms.TextInput(attrs={"type": "tel", "placeholder": "+998 90 123 45 67", "autocomplete": "tel"}),
    )
    # Architects sign in with phone + password; clients with their phone number alone.
    password = forms.CharField(
        label="Parol (faqat arxitektorlar uchun)", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
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
                # An architect who has a password must give it. (Architects from before passwords
                # existed have none yet: they get in and are asked to create one straight away.)
                if user.role == user.Role.ARCHITECT and user.has_usable_password():
                    if not user.check_password(cleaned.get("password") or ""):
                        raise forms.ValidationError("Parol noto'g'ri. Arxitektorlar telefon raqami va parol bilan kiradi.")
                cleaned["user"] = user
                return cleaned
        raise forms.ValidationError("Bu telefon raqami bilan hisob topilmadi.")
