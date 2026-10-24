from django import forms

from applications.models import Application
from poydevor.upload_safety import ACCEPT_ATTRIBUTE, validate_pdf_or_jpg


class ApplicationForm(forms.ModelForm):
    size_unknown = forms.BooleanField(required=False, label="Bilmayman, taxminan hisoblang")

    class Meta:
        model = Application
        fields = [
            "size_m2", "size_unknown", "rooms_count", "location", "interior_style", "budget", "description", "plan_pdf",
        ]
        labels = {
            "size_m2": "Maydon (m²)", "rooms_count": "Xonalar soni",
            "location": "Manzil", "interior_style": "Interyer uslubi (ixtiyoriy)",
            "budget": "Byudjet (ixtiyoriy)", "description": "Nima qilish kerak? (ixtiyoriy)",
            "plan_pdf": "Uy rasmi (ixtiyoriy)",
        }

        widgets = {
            "description": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Masalan: 2 qavatli zamonaviy uy loyihasi, hovli va garaj bilan. Ichki dizayn ham kerak.",
            }),
            # PDF or JPG only; clean_plan_pdf checks the real content (poydevor/upload_safety.py).
            "plan_pdf": forms.ClearableFileInput(attrs={"accept": ACCEPT_ATTRIBUTE}),
        }

    def clean_plan_pdf(self):
        upload = self.cleaned_data.get("plan_pdf")
        if upload and hasattr(upload, "size"):
            validate_pdf_or_jpg(upload, max_mb=20)
        return upload

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("size_unknown"):
            cleaned["size_m2"] = None
        elif not cleaned.get("size_m2"):
            self.add_error("size_m2", "Maydonni kiriting yoki 'Bilmayman' belgisini qo'ying.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get("size_unknown"):
            instance.size_m2 = None
        if commit:
            instance.save()
        return instance
