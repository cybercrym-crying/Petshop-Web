from django import forms

from .models import FaqEntry


class FaqForm(forms.ModelForm):
    class Meta:
        model = FaqEntry
        fields = ["question", "answer", "keywords", "link_url", "link_label", "order", "is_quick", "is_active"]

    def clean_link_url(self):
        url = (self.cleaned_data.get("link_url") or "").strip()
        if url and not (url.startswith("/") and not url.startswith("//") or url.startswith("https://")):
            raise forms.ValidationError("Tautan harus diawali '/' (halaman toko) atau 'https://'.")
        return url
