import os
from datetime import date

from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from accounts.forms import NewPhoneField
from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject, Studio
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
    email = forms.EmailField(label="Email address")
    phone = NewPhoneField()

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            del self.fields["phone"]

    def clean(self):
        cleaned = super().clean()
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
    studio_name = forms.CharField(label="Studio nomi", max_length=150)
    founded_on = forms.DateField(label="Qachon asos solingan", widget=forms.DateInput(attrs={"type": "date"}))
    founders = forms.CharField(label="Asoschilar", max_length=255)
    responsible_person = forms.CharField(label="Mas'ul shaxs F.I.Sh.", max_length=150)
    responsible_birth_date = forms.DateField(label="Tug'ilgan sanasi", widget=forms.DateInput(attrs={"type": "date"}))
    staff_count = forms.IntegerField(label="Studiyada nechta odam ishlaydi", min_value=1)
    projects_count = forms.IntegerField(label="Qancha loyiha bajarilgan", min_value=0)

    field_order = [
        "avatar", "studio_name", "founded_on", "founders", "responsible_person", "responsible_birth_date",
        "email", "phone", "staff_count", "projects_count",
    ]


class EmployeeRegistrationForm(RegistrationForm):
    full_name = forms.CharField(label="Ism va Familiya", max_length=200)
    birth_year = _birth_year_field()
    studio = forms.ModelChoiceField(
        queryset=Studio.objects.none(), label="Qaysi Studiya a'zosi sifatida qo'shilmoqchisiz",
        empty_label="Studiyani tanlang",
    )

    field_order = ["avatar", "full_name", "birth_year", "phone", "email", "studio"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["studio"].queryset = Studio.objects.filter(
            owner__approval_status=ArchitectProfile.ApprovalStatus.APPROVED,
        )


class FreelancerRegistrationForm(RegistrationForm):
    full_name = forms.CharField(label="Ism va Familiya", max_length=200)
    birth_year = _birth_year_field()
    projects_count = forms.IntegerField(label="Shu paytgacha nechta loyiha amalga oshirgan", min_value=0)

    field_order = ["avatar", "full_name", "birth_year", "phone", "email", "projects_count"]


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


class PortfolioProjectEditForm(forms.ModelForm):
    """The details of a portfolio project: title, type, description (optional) and its
    one file. The file is required; when editing a project that already has one, the
    old file stays unless a new one is chosen."""

    class Meta:
        model = PortfolioProject
        fields = ["title", "style", "description", "attachment"]
        labels = {
            "title": "Loyiha nomi",
            "style": "Loyiha turi (uslubi)",
            "description": "Loyiha tavsifi (ixtiyoriy)",
            "attachment": "Loyiha fayli",
        }
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Masalan: Ikki qavatli zamonaviy uy"}),
            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Loyiha haqida yozing: maydoni, vazifasi, qanday yechimlar qo'llanilgani...",
            }),
            # PDF or JPG only; clean_attachment checks the real content (poydevor/upload_safety.py).
            "attachment": forms.FileInput(attrs={"accept": ACCEPT_ATTRIBUTE}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["style"].required = True
        self.fields["style"].empty_label = "Turini tanlang"
        self.fields["description"].required = False
        # A new project needs its file; an existing one already has it.
        self.fields["attachment"].required = not (self.instance.pk and self.instance.attachment)
        self.fields["attachment"].error_messages["required"] = "Loyiha faylini yuklang."

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
