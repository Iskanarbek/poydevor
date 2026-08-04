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


class ArchitectOnboardingForm(ArchitectProfileForm):
    """Onboarding requires a minimal portfolio: bio (already required by
    the model field) plus at least one skill. ``portfolio_edit`` keeps
    using the base ``ArchitectProfileForm`` with skills optional, since an
    existing profile with zero skills shouldn't become invalid to edit."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["skills"].required = True


class PortfolioProjectForm(forms.ModelForm):
    class Meta:
        model = PortfolioProject
        fields = ["title", "description", "style"]


class PortfolioImageForm(forms.ModelForm):
    class Meta:
        model = PortfolioImage
        fields = ["image"]
