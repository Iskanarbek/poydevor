import os

from django import forms

from applications.models import HOUSE_IMAGE_EXTENSIONS, Application

ALLOWED_HOUSE_FILES = HOUSE_IMAGE_EXTENSIONS | {".pdf"}


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
            "plan_pdf": forms.ClearableFileInput(attrs={"accept": "image/*,.pdf"}),
        }

    def clean_plan_pdf(self):
        upload = self.cleaned_data.get("plan_pdf")
        if upload and hasattr(upload, "size"):
            if os.path.splitext(upload.name)[1].lower() not in ALLOWED_HOUSE_FILES:
                raise forms.ValidationError("Uy rasmini JPG, PNG, WEBP yoki PDF ko'rinishida yuklang.")
            if upload.size > 20 * 1024 * 1024:
                raise forms.ValidationError("Fayl juda katta (eng ko'pi 20 MB).")
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
