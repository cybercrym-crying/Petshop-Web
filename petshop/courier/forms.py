from django import forms

from common.photos import clean_photo

from .models import CourierProfile


class CourierProfileForm(forms.ModelForm):
    class Meta:
        model = CourierProfile
        fields = ["vehicle", "plate_number", "service_area", "status", "can_carry_pets"]
        widgets = {
            "vehicle": forms.TextInput(attrs={"class": "form-control"}),
            "plate_number": forms.TextInput(attrs={"class": "form-control"}),
            "service_area": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }




class ProblemForm(forms.Form):
    """Paket gagal diantar: alasan wajib, foto kondisi di lokasi opsional (dari kamera)."""

    note = forms.CharField(max_length=255)
    photo = forms.ImageField(required=False)

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        return clean_photo(photo) if photo else None
