import os
import re
from datetime import date

from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from accounts.forms import NewPhoneField
from architects.models import (
    SERVICE_TYPE_FORM_LABELS, SINGLE_SERVICES, ArchitectProfile, ObjectType, PortfolioImage, PortfolioProject, ServiceType, Studio, Style,
)
from poydevor.upload_safety import ACCEPT_ATTRIBUTE, validate_pdf_or_jpg

PORTFOLIO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".pdf", ".mp4", ".mov", ".webm",
}  # kept for the file-upload widget defaults


class ArchitectProfileForm(forms.ModelForm):
    class Meta:
        model = ArchitectProfile
        fields = ["bio", "telegram_username", "avatar", "styles", "skills"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
            "styles": forms.CheckboxSelectMultiple,
            "skills": forms.CheckboxSelectMultiple,
        }


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True
    # The visible "add files" uploader (see _portfolio_uploader.html) fills this
    # hidden input and shows its own message when there are too few files.
    use_required_attribute = lambda self, initial: False  # noqa: E731

    def value_from_datadict(self, data, files, name):
        # Always return *every* uploaded file. Older Django versions (4.2) only hand back
        # the last one here, which made a 10-photo upload look like a single file.
        getlist = getattr(files, "getlist", None)
        return getlist(name) if getlist else files.get(name)


class MultipleFileField(forms.FileField):
    """A file field that accepts several files at once and cleans to a list."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={
            "accept": ",".join(sorted(PORTFOLIO_EXTENSIONS)),
            "hidden": True,
            "x-ref": "real",
        }))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        return [single_clean(data, initial)]


class RegistrationForm(forms.Form):
    """Base for the three architect sign-up forms.

    ``user`` is only passed for a signed-in architect who never finished
    registering: their phone number is already known, so it isn't asked again.
    """

    avatar = forms.ImageField(
        label="Profil rasmi", required=False,
        widget=forms.FileInput(attrs={"accept": "image/*"}),
    )
    phone = NewPhoneField()
    # Any password will do (even a single character): there are deliberately no strength rules.
    password = forms.CharField(
        label="Parol o'ylab toping", min_length=1, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Istalgan parol bo'ladi. Keyingi safar telefon raqamingiz va shu parol bilan kirasiz.",
    )
    password_confirm = forms.CharField(
        label="Parolni takrorlang", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    telegram_username = forms.CharField(
        label="Telegram akkauntingiz (ixtiyoriy)", max_length=50, required=False,
        widget=forms.TextInput(attrs={"placeholder": "@username"}),
        help_text="Mijoz siz bilan Telegram orqali bog'lanadi.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            del self.fields["phone"]

    def clean_telegram_username(self):
        value = self.cleaned_data["telegram_username"].strip()
        if not value:
            return ""
        value = re.sub(r"^(?:https?://)?(?:t\.me/|telegram\.me/)", "", value).lstrip("@").rstrip("/")
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", value):
            raise forms.ValidationError("Telegram username noto'g'ri. Masalan: @poydevor_uz (5–32 ta harf, raqam yoki _).")
        return value

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("password_confirm") is not None \
                and cleaned["password"] != cleaned["password_confirm"]:
            self.add_error("password_confirm", "Parollar bir xil emas.")
        if self.user is not None:
            cleaned["phone"] = self.user.phone
        return cleaned


def _birth_year_field():
    this_year = date.today().year
    return forms.IntegerField(
        label="Tug'ilgan yil", min_value=1940, max_value=this_year - 16,
        widget=forms.NumberInput(attrs={"placeholder": "1995"}),
    )


class StudioRegistrationForm(RegistrationForm):
    # A studio is shown by its logo and name, not by the owner's face (saved as the profile picture).
    avatar = forms.ImageField(
        label="Studiya logotipi",
        widget=forms.FileInput(attrs={"accept": "image/*"}),
        help_text="Mijozlar studiyangizni shu logotip va nom bilan ko'radi.",
    )
    studio_name = forms.CharField(label="Studio nomi", max_length=150)
    founded_year = forms.IntegerField(
        label="Qaysi yilda asos solingan", min_value=1900, max_value=date.today().year,
        widget=forms.NumberInput(attrs={"placeholder": "2018"}),
    )
    responsible_person = forms.CharField(label="Mas'ul shaxs F.I.Sh.", max_length=150)
    responsible_birth_date = forms.DateField(label="Mas'ul shaxsning tug'ilgan sanasi", widget=forms.DateInput(attrs={"type": "date"}))

    field_order = [
        "avatar", "studio_name", "founded_year", "responsible_person", "responsible_birth_date",
        "phone", "telegram_username", "password", "password_confirm",
    ]


class EmployeeRegistrationForm(RegistrationForm):
    full_name = forms.CharField(label="Ism va Familiya", max_length=200)
    birth_year = _birth_year_field()
    studio = forms.ModelChoiceField(
        queryset=Studio.objects.none(), label="Qaysi Studiya a'zosi sifatida qo'shilmoqchisiz",
        empty_label="Studiyani tanlang",
    )

    field_order = ["avatar", "full_name", "birth_year", "phone", "telegram_username", "password", "password_confirm", "studio"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["studio"].queryset = Studio.objects.filter(
            owner__approval_status=ArchitectProfile.ApprovalStatus.APPROVED,
        )


class FreelancerRegistrationForm(RegistrationForm):
    full_name = forms.CharField(label="Ism va Familiya", max_length=200)
    birth_year = _birth_year_field()

    field_order = ["avatar", "full_name", "birth_year", "phone", "telegram_username", "password", "password_confirm"]


class PortfolioImagesForm(forms.Form):
    """Several photos for one portfolio project, uploaded together."""

    images = MultipleFileField(
        label="Rasmlar",
        widget=MultipleFileInput(attrs={"accept": ",".join(sorted(IMAGE_EXTENSIONS)), "hidden": True, "x-ref": "real"}),
    )

    def clean_images(self):
        return _check_images(self.cleaned_data["images"])


def _check_images(files):
    if not files:
        raise forms.ValidationError("Kamida bitta rasm qo'shing.")
    max_bytes = settings.PORTFOLIO_MAX_FILE_MB * 1024 * 1024
    for uploaded in files:
        if os.path.splitext(uploaded.name)[1].lower() not in IMAGE_EXTENSIONS:
            raise forms.ValidationError(f"«{uploaded.name}» rasm emas (JPG, PNG, WEBP yoki GIF yuklang).")
        if uploaded.size > max_bytes:
            raise forms.ValidationError(f"«{uploaded.name}» juda katta (eng ko'pi {settings.PORTFOLIO_MAX_FILE_MB} MB).")
    return files


OTHER_STYLE = "other"


class ServiceTypeField(forms.MultipleChoiceField):
    """Tick one or both services. Both ticked is stored as "both"."""

    widget = forms.CheckboxSelectMultiple

    def __init__(self, **kwargs):
        kwargs.setdefault("choices", [(v, SERVICE_TYPE_FORM_LABELS[v]) for v in SINGLE_SERVICES])
        super().__init__(**kwargs)

    def to_python(self, value):
        return super().to_python([value] if isinstance(value, str) else value)

    def prepare_value(self, value):
        if value == ServiceType.BOTH:
            return [str(v) for v in SINGLE_SERVICES]
        return [value] if isinstance(value, str) and value else value

    def clean(self, value):
        chosen = super().clean(value)
        return ServiceType.BOTH if set(chosen) == {str(v) for v in SINGLE_SERVICES} else chosen[0]


class StyleSelect(forms.Select):
    """The list of styles plus a last choice, "Boshqa", for people whose style is not listed."""

    def optgroups(self, name, value, attrs=None):
        groups = super().optgroups(name, value, attrs)
        picked = OTHER_STYLE in [str(v) for v in value]
        groups.append((None, [{
            "name": name, "value": OTHER_STYLE, "label": "Boshqa (o'zim yozaman)", "selected": picked,
            "index": str(len(groups)), "attrs": {"selected": True} if picked else {},
            "type": self.input_type, "template_name": self.option_template_name, "wrap_label": True,
        }], len(groups)))
        return groups


class StyleChoiceField(forms.ModelChoiceField):
    widget = StyleSelect

    def to_python(self, value):
        return None if value == OTHER_STYLE else super().to_python(value)


class OwnStyleFormMixin:
    """An optional style that can also be written in by hand.

    ``style_field`` names the model's style field. When "Boshqa" is chosen the person's own
    words (``custom_style``) are required and saved instead of a listed style; otherwise
    ``custom_style`` is cleared. Add ``custom_style`` to the form's Meta.fields."""

    style_field = "style"

    style_required = False      # architects must choose a style (or "Boshqa" and write it); clients need not

    def setup_style(self, label, required=False):
        self.style_required = required
        self.fields[self.style_field] = StyleChoiceField(
            queryset=Style.objects.all(), required=False,         # "required" is enforced in clean(): "Boshqa" has no row
            empty_label="Uslubni tanlang" if required else "Tanlamayman", label=label,
        )
        self.fields["custom_style"] = forms.CharField(
            required=False, max_length=60, label="Uslubni o'zingiz yozing",
            widget=forms.TextInput(attrs={"placeholder": "Masalan: Skandinav, Art-deko, Yaponcha..."}),
        )
        instance = getattr(self, "instance", None)
        if instance is not None and instance.pk and instance.custom_style and not getattr(instance, f"{self.style_field}_id"):
            self.initial[self.style_field] = OTHER_STYLE

    def clean(self):
        cleaned = super().clean()
        if self.data.get(self.add_prefix(self.style_field)) == OTHER_STYLE:
            text = (cleaned.get("custom_style") or "").strip()
            if not text:
                self.add_error("custom_style", "Uslub nomini yozing.")
            cleaned["custom_style"] = text
            cleaned[self.style_field] = None
        else:
            cleaned["custom_style"] = ""
            if self.style_required and not cleaned.get(self.style_field):
                self.add_error(self.style_field, "Uslubni tanlang (yoki «Boshqa»ni tanlab, o'zingiz yozing).")
        return cleaned


class PortfolioProjectEditForm(OwnStyleFormMixin, forms.ModelForm):
    """The details of a portfolio project: title, type, description (optional) and its
    one file. The file is required; when editing a project that already has one, the
    old file stays unless a new one is chosen."""

    class Meta:
        model = PortfolioProject
        fields = [
            "title", "object_type", "service_type", "style", "custom_style", "price_usd", "description", "attachment",
        ]
        labels = {
            "title": "Loyiha nomi",
            "object_type": "Obyekt turi",
            "service_type": "Xizmat turi",
            "price_usd": "Loyiha narxi, $ (ixtiyoriy)",
            "description": "Nima qilingan? (ixtiyoriy)",
            "attachment": "Loyiha fayli (ixtiyoriy)",
        }
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Masalan: Ikki qavatli zamonaviy uy"}),
            "price_usd": forms.NumberInput(attrs={"placeholder": "Masalan: 1500", "min": 0}),
            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Qisqa yozing: nima qildingiz, qanday yechimlar qo'lladingiz. Mijozlar buni kartochkada ko'radi.",
            }),
            # PDF or JPG only; clean_attachment checks the real content (poydevor/upload_safety.py).
            "attachment": forms.FileInput(attrs={"accept": ACCEPT_ATTRIBUTE}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_style("Loyiha uslubi", required=True)
        self.fields["object_type"] = forms.ChoiceField(
            label="Obyekt turi",
            choices=[("", "Tanlang")] + list(ObjectType.choices),
            error_messages={"required": "Obyekt turini tanlang."},
        )
        self.fields["service_type"] = ServiceTypeField(
            label="Xizmat turi (ikkalasini ham tanlash mumkin)",
            error_messages={"required": "Xizmat turini tanlang."},
        )
        self.fields["price_usd"].required = False
        self.fields["description"].required = False
        # The project file is optional.
        self.fields["attachment"].required = False

    def clean_attachment(self):
        upload = self.cleaned_data.get("attachment")
        if isinstance(upload, UploadedFile):   # an unchanged, already stored file is left alone
            validate_pdf_or_jpg(upload, max_mb=settings.PORTFOLIO_MAX_FILE_MB)
        return upload


class PortfolioProjectForm(PortfolioProjectEditForm):
    """A whole portfolio project in one step: the details plus its photos (at least
    one; the first is the cover)."""

    images = MultipleFileField(
        label="Rasmlar",
        widget=MultipleFileInput(attrs={"accept": ",".join(sorted(IMAGE_EXTENSIONS)), "hidden": True, "x-ref": "real"}),
    )

    def clean_images(self):
        return _check_images(self.cleaned_data["images"])
