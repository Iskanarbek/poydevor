from django import forms

from applications.models import Application


class ApplicationForm(forms.ModelForm):
    size_unknown = forms.BooleanField(required=False, label="Bilmayman, taxminan hisoblang")

    class Meta:
        model = Application
        fields = ["size_m2", "size_unknown", "rooms_count", "location", "interior_style", "budget", "plan_pdf"]
        labels = {
            "size_m2": "Maydon (m²)", "rooms_count": "Xonalar soni",
            "location": "Manzil", "interior_style": "Interyer uslubi (ixtiyoriy)",
            "budget": "Byudjet (ixtiyoriy)", "plan_pdf": "Uy rejasi, PDF (ixtiyoriy)",
        }

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
