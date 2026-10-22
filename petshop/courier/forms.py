from django import forms

from .models import CourierProfile


class CourierProfileForm(forms.ModelForm):
    class Meta:
        model = CourierProfile
        fields = ["vehicle", "plate_number", "service_area", "status"]
        widgets = {
            "vehicle": forms.TextInput(attrs={"class": "form-control"}),
            "plate_number": forms.TextInput(attrs={"class": "form-control"}),
            "service_area": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }


MAX_PROOF_SIZE = 10 * 1024 * 1024  # 10 MB, cukup untuk foto kamera HP
ALLOWED_PROOF_FORMATS = {"JPEG", "PNG", "WEBP"}


class DeliveryProofForm(forms.Form):
    """Bukti sampai: foto wajib, catatan (mis. 'diterima satpam') opsional."""

    photo = forms.ImageField(
        label="Foto bukti penerimaan",
        error_messages={
            "required": "Foto bukti wajib dilampirkan untuk menyelesaikan pengiriman.",
            "invalid_image": "File harus berupa foto (JPG, PNG, atau WEBP).",
        },
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "image/*", "capture": "environment"}
        ),
    )
    note = forms.CharField(
        label="Catatan",
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Opsional, mis. diterima langsung oleh pembeli",
            }
        ),
    )

    def clean_photo(self):
        photo = self.cleaned_data["photo"]
        if photo.size > MAX_PROOF_SIZE:
            raise forms.ValidationError("Ukuran foto maksimal 10 MB.")
        image_format = getattr(getattr(photo, "image", None), "format", None)
        if image_format not in ALLOWED_PROOF_FORMATS:
            raise forms.ValidationError("Format foto harus JPG, PNG, atau WEBP.")
        return photo
