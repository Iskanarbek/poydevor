from django import forms

from architects.models import ArchitectProfile, PortfolioImage, PortfolioProject


class ArchitectProfileForm(forms.ModelForm):
    class Meta:
        model = ArchitectProfile
        fields = ["bio", "telegram_username", "avatar", "styles", "skills"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
            "styles": forms.CheckboxSelectMultiple,
            "skills": forms.CheckboxSelectMultiple,
        }


class PortfolioProjectForm(forms.ModelForm):
    class Meta:
        model = PortfolioProject
        fields = ["title", "description", "style", "order"]


class PortfolioImageForm(forms.ModelForm):
    class Meta:
        model = PortfolioImage
        fields = ["image", "order"]
