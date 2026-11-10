from django import forms

from applications.models import Application, ApplicationFile
from applications.pricing import estimate_price
from architects.forms import MultipleFileField, MultipleFileInput, OwnStyleFormMixin, ServiceTypeField
from architects.models import ObjectType
from poydevor.upload_safety import PHOTO_ACCEPT_ATTRIBUTE, validate_pdf_or_photo


class ApplicationForm(OwnStyleFormMixin, forms.ModelForm):
    """Posting an order. Every question about the object is required, the house photo or
    cadastre must be uploaded, and the client has to agree to the market estimate."""

    style_field = "interior_style"
    MAX_FILES = 10

    # Several photos / files at once (house pictures, cadastre, plans), all optional.
    files = MultipleFileField(
        required=False, label="Uy rasmi yoki kadastr (ixtiyoriy)",
        widget=MultipleFileInput(attrs={"accept": PHOTO_ACCEPT_ATTRIBUTE, "multiple": True}),
    )

    price_confirmed = forms.BooleanField(
        required=True, label="Taxminiy narxga roziman",
        error_messages={"required": "Davom etish uchun taxminiy narxni tasdiqlang."},
    )

    class Meta:
        model = Application
        fields = [
            "size_m2", "object_type", "service_type", "rooms_count", "location",
            "interior_style", "custom_style", "description",
        ]
        labels = {
            "size_m2": "Obyektning umumiy maydoni qancha? (m²)",
            "rooms_count": "Xonalar soni",
            "location": "Manzil (shahar yoki viloyat)",
            "description": "Nima qilish kerak? (ixtiyoriy)",
        }
        widgets = {
            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Masalan: 2 qavatli zamonaviy uy loyihasi, hovli va garaj bilan. Ichki dizayn ham kerak.",
            }),
            "size_m2": forms.NumberInput(attrs={"min": 1, "placeholder": "Masalan: 120"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_style("Interyer uslubi (ixtiyoriy)")
        self.fields["size_m2"].required = True
        self.fields["size_m2"].min_value = 1
        self.fields["object_type"] = forms.ChoiceField(
            label="Qanday turdagi obyekt bo'yicha xizmat kerak?", choices=ObjectType.choices, widget=forms.RadioSelect,
            error_messages={"required": "Obyekt turini tanlang."},
        )
        self.fields["service_type"] = ServiceTypeField(
            label="Qanday xizmat talab etiladi? (ikkalasini ham tanlash mumkin)",
            error_messages={"required": "Xizmat turini tanlang."},
        )
        self.fields["location"].required = True
        self.fields["rooms_count"].required = True

    def clean_files(self):
        uploads = [u for u in (self.cleaned_data.get("files") or []) if u]
        if len(uploads) > self.MAX_FILES:
            raise forms.ValidationError(f"Ko'pi bilan {self.MAX_FILES} ta fayl yuklash mumkin.")
        for upload in uploads:
            validate_pdf_or_photo(upload, max_mb=20)
        return uploads

    def save_files(self, application):
        """Attach the uploaded photos/files to the saved order."""
        for upload in self.cleaned_data.get("files") or []:
            ApplicationFile.objects.create(application=application, file=upload)

    def save(self, commit=True):
        instance = super().save(commit=False)
        # The estimate is worked out here from the answers (never taken from the browser).
        estimate = estimate_price(
            instance.size_m2, instance.object_type, instance.service_type, instance.rooms_count, instance.location,
        )
        if estimate:
            instance.estimate_min, instance.estimate_max = estimate
        if commit:
            instance.save()
        return instance
