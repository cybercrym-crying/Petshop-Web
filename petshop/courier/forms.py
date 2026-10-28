from django import forms

from common.photos import clean_photo

from account.form import _clean_phone
from account.models import User

from .models import CourierProfile


class CourierProfileForm(forms.ModelForm):
    class Meta:
        model = CourierProfile
        fields = ["vehicle", "plate_number", "service_area", "status"]
        labels = {"vehicle": "Kendaraan", "plate_number": "Nomor polisi", "service_area": "Area layanan"}
        widgets = {
            "vehicle": forms.TextInput(attrs={"class": "form-control"}),
            "plate_number": forms.TextInput(attrs={"class": "form-control"}),
            "service_area": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }




class CourierAccountForm(forms.ModelForm):
    """Kurir mengubah data akunnya sendiri. Area layanan dan status tetap diatur admin."""

    name = forms.CharField(max_length=255, label="Nama lengkap")
    phone_number = forms.CharField(max_length=20, label="Nomor WhatsApp")
    vehicle = forms.CharField(max_length=50, required=False, label="Kendaraan")
    plate_number = forms.CharField(max_length=20, required=False, label="Nomor polisi")
    photo = forms.ImageField(
        required=False,
        label="Foto kurir",
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        help_text="Foto wajah yang jelas. Tampil untuk pelanggan saat paket diantar. JPG/PNG/WEBP, maks. 10 MB.",
        error_messages={"invalid_image": "File harus berupa foto (JPG, PNG, atau WEBP)."},
    )
    remove_photo = forms.BooleanField(required=False, label="Hapus foto")

    class Meta:
        model = User
        fields = ["email"]
        labels = {"email": "Email (opsional)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile, _ = CourierProfile.objects.get_or_create(user=self.instance)
        self.fields["name"].initial = self.instance.name
        self.fields["phone_number"].initial = self.instance.phone_number
        self.fields["vehicle"].initial = self.profile.vehicle
        self.fields["plate_number"].initial = self.profile.plate_number
        self.order_fields(["photo", "remove_photo", "name", "phone_number", "email", "vehicle", "plate_number"])

    def clean_phone_number(self):
        return _clean_phone(self.cleaned_data["phone_number"])

    def clean_plate_number(self):
        return " ".join(self.cleaned_data["plate_number"].upper().split())

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        return clean_photo(photo) if photo else None

    def save(self, commit=True):
        user = super().save(commit=False)
        user.name = self.cleaned_data["name"]
        user.phone_number = self.cleaned_data["phone_number"]
        profile = self.profile
        profile.vehicle = self.cleaned_data["vehicle"].strip()
        profile.plate_number = self.cleaned_data["plate_number"]
        old_photo = profile.photo.name if profile.photo else ""
        if self.cleaned_data.get("photo"):
            profile.photo = self.cleaned_data["photo"]
        elif self.cleaned_data.get("remove_photo"):
            profile.photo = None
        if commit:
            user.save()
            profile.save()
            new_photo = profile.photo.name if profile.photo else ""
            if old_photo and old_photo != new_photo:
                profile.photo.storage.delete(old_photo)
        return user


class ProblemForm(forms.Form):
    """Paket gagal diantar: alasan wajib, foto kondisi di lokasi opsional (dari kamera)."""

    note = forms.CharField(max_length=255)
    photo = forms.ImageField(required=False)

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        return clean_photo(photo) if photo else None
