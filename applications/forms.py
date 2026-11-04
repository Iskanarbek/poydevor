from django import forms

from applications.models import Application
from applications.pricing import estimate_price
from architects.forms import OwnStyleFormMixin
from architects.models import SERVICE_TYPE_FORM_LABELS, ObjectType, ServiceType
from poydevor.upload_safety import ACCEPT_ATTRIBUTE, validate_pdf_or_jpg


class ApplicationForm(OwnStyleFormMixin, forms.ModelForm):
    """Posting an order. Every question about the object is required, the house photo or
    cadastre must be uploaded, and the client has to agree to the market estimate."""

    style_field = "interior_style"

    price_confirmed = forms.BooleanField(
        required=True, label="Taxminiy narxga roziman",
        error_messages={"required": "Davom etish uchun taxminiy narxni tasdiqlang."},
    )

    class Meta:
        model = Application
        fields = [
            "size_m2", "object_type", "service_type", "rooms_count", "location",
            "interior_style", "custom_style", "budget", "description", "plan_pdf",
        ]
        labels = {
            "size_m2": "Obyektning umumiy maydoni qancha? (m²)",
            "rooms_count": "Xonalar soni",
            "location": "Manzil (shahar yoki viloyat)",
            "budget": "Byudjet (ixtiyoriy)",
            "description": "Nima qilish kerak? (ixtiyoriy)",
            "plan_pdf": "Uy rasmi yoki kadastr",
        }
        widgets = {
            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Masalan: 2 qavatli zamonaviy uy loyihasi, hovli va garaj bilan. Ichki dizayn ham kerak.",
            }),
            "size_m2": forms.NumberInput(attrs={"min": 1, "placeholder": "Masalan: 120"}),
            # PDF or JPG only; clean_plan_pdf checks the real content (poydevor/upload_safety.py).
            "plan_pdf": forms.ClearableFileInput(attrs={"accept": ACCEPT_ATTRIBUTE}),
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
        self.fields["service_type"] = forms.ChoiceField(
            label="Qanday xizmat talab etiladi?",
            choices=[(v, SERVICE_TYPE_FORM_LABELS[v]) for v in ServiceType.values], widget=forms.RadioSelect,
            error_messages={"required": "Xizmat turini tanlang."},
        )
        self.fields["plan_pdf"].required = True
        self.fields["plan_pdf"].error_messages["required"] = "Uy rasmini yoki kadastrni yuklang."
        self.fields["location"].required = True
        self.fields["rooms_count"].required = True

    def clean_plan_pdf(self):
        upload = self.cleaned_data.get("plan_pdf")
        if upload and hasattr(upload, "size"):
            validate_pdf_or_jpg(upload, max_mb=20)
        return upload

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
