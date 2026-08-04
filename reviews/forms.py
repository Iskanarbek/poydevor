from django import forms


class ReviewForm(forms.Form):
    rating = forms.ChoiceField(choices=[(i, str(i)) for i in range(1, 6)], label="Baho")
    comment = forms.CharField(widget=forms.Textarea, required=False, label="Izoh")
