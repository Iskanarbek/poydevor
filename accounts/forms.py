from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth import password_validation

from accounts.models import User


class SignupForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label="Parol")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "role"]
        widgets = {"role": forms.RadioSelect}
        labels = {
            "first_name": "Ism", "last_name": "Familiya",
            "phone": "Telefon raqami",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("Bu telefon raqami band, boshqasini kiriting.")
        return phone

    def clean_password(self):
        password = self.cleaned_data["password"]
        user = User(
            first_name=self.data.get("first_name", ""),
            last_name=self.data.get("last_name", ""),
            phone=self.data.get("phone", ""),
        )
        try:
            password_validation.validate_password(password, user=user)
        except forms.ValidationError as error:
            raise forms.ValidationError(error.messages)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    phone = forms.CharField(label="Telefon raqami")
    password = forms.CharField(widget=forms.PasswordInput, label="Parol")

    def clean(self):
        cleaned = super().clean()
        user = authenticate(phone=cleaned.get("phone"), password=cleaned.get("password"))
        if user is None:
            raise forms.ValidationError("Telefon raqami yoki parol noto'g'ri.")
        cleaned["user"] = user
        return cleaned
