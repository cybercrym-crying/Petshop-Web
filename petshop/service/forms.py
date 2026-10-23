from datetime import time, timedelta

from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from account.models import Customer, User
from common.photos import CameraPhotoForm, clean_photo
from product.models import PetType

from .models import Pet, Service, ServiceStep

OPEN_HOUR = time(8, 0)
CLOSE_HOUR = time(20, 0)
MAX_DAYS_AHEAD = 60
DATETIME_LOCAL = "%Y-%m-%dT%H:%M"

PET_CHOICES = [(code, label) for code, label in PetType.choices if code != PetType.ALL]


def _schedule_widget():
    return forms.DateTimeInput(
        attrs={"type": "datetime-local", "step": 900}, format=DATETIME_LOCAL
    )


class BookingForm(forms.Form):
    """Form booking dari situs pelanggan."""

    service = forms.ModelChoiceField(
        queryset=Service.objects.active(),
        label=_("Layanan"),
        empty_label=_("Pilih layanan"),
    )
    pet = forms.ModelChoiceField(
        queryset=Pet.objects.none(),
        required=False,
        label=_("Hewan saya"),
        empty_label=_("Hewan baru (isi nama & jenis)"),
    )
    pet_name = forms.CharField(max_length=60, label=_("Nama hewan"), required=False)
    pet_type = forms.ChoiceField(choices=[("", _("Pilih jenis"))] + PET_CHOICES, label=_("Jenis hewan"), required=False)
    schedule = forms.DateTimeField(
        label=_("Jadwal datang"),
        input_formats=[DATETIME_LOCAL, "%Y-%m-%d %H:%M"],
        widget=_schedule_widget(),
    )
    note = forms.CharField(
        max_length=255,
        required=False,
        label=_("Catatan"),
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": _("Opsional, mis. kulit sensitif / galak saat potong kuku")}),
    )

    pickup = forms.BooleanField(required=False, label=_("Jemput hewan di rumah"))
    return_trip = forms.BooleanField(required=False, label=_("Antar pulang setelah selesai"))
    address = forms.CharField(max_length=255, required=False, label=_("Alamat jemput/antar"))
    latitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, min_value=-90, max_value=90,
                                  widget=forms.HiddenInput(attrs={"data-map-lat": ""}))
    longitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, min_value=-180, max_value=180,
                                   widget=forms.HiddenInput(attrs={"data-map-lng": ""}))

    allow_past = False

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        if customer is not None and "pet" in self.fields:
            self.fields["pet"].queryset = Pet.objects.filter(owner=customer, is_active=True)
        if "pet" in self.fields and not self.fields["pet"].queryset.exists():
            self.fields["pet"].widget = forms.HiddenInput()

    @property
    def location(self):
        lat, lng = self.cleaned_data.get("latitude"), self.cleaned_data.get("longitude")
        return (lat, lng) if lat is not None and lng is not None else None

    def clean_schedule(self):
        schedule = self.cleaned_data["schedule"]
        local = timezone.localtime(schedule)
        now = timezone.localtime()
        if not self.allow_past and schedule < now:
            raise forms.ValidationError(_("Jadwal harus setelah waktu sekarang."))
        if self.allow_past and local.date() < now.date():
            raise forms.ValidationError(_("Jadwal tidak boleh di hari yang sudah lewat."))
        if schedule > now + timedelta(days=MAX_DAYS_AHEAD):
            raise forms.ValidationError(
                f"Booking paling lambat {MAX_DAYS_AHEAD} hari dari sekarang."
            )
        if not (OPEN_HOUR <= local.time() <= CLOSE_HOUR):
            raise forms.ValidationError(
                f"Jam layanan {OPEN_HOUR:%H.%M}–{CLOSE_HOUR:%H.%M} WITA."
            )
        return schedule

    def clean(self):
        cleaned = super().clean()
        chosen = cleaned.get("pet")
        if chosen:
            cleaned["pet_name"], cleaned["pet_type"] = chosen.name, chosen.pet_type
        else:
            if not cleaned.get("pet_name", "").strip():
                self.add_error("pet_name", _("Isi nama hewan atau pilih dari Hewan Saya."))
            if not cleaned.get("pet_type"):
                self.add_error("pet_type", _("Pilih jenis hewan."))
        if (cleaned.get("pickup") or cleaned.get("return_trip")) and self.location is None:
            self.add_error("address", _("Tandai lokasi jemput/antar di peta."))
        service, pet = cleaned.get("service"), cleaned.get("pet_type")
        if service and pet and not service.suits(pet):
            self.add_error(
                "service",
                f"Layanan ini khusus {service.get_pet_type_display().lower()}.",
            )
        schedule = cleaned.get("schedule")
        if service and schedule:
            local = timezone.localtime(schedule)
            finish = local + timedelta(minutes=service.duration_minutes)
            closing = local.replace(
                hour=CLOSE_HOUR.hour, minute=CLOSE_HOUR.minute, second=0, microsecond=0
            )
            if finish > closing:
                self.add_error(
                    "schedule",
                    f"Layanan ini butuh ± {service.duration_minutes} menit dan harus "
                    f"selesai sebelum {CLOSE_HOUR:%H.%M} WITA. Pilih jam lebih awal.",
                )
        return cleaned


class StaffBookingForm(BookingForm):
    """Booking yang dibuat admin/kasir untuk pelanggan yang datang langsung."""

    customer = forms.ModelChoiceField(
        queryset=Customer.objects.order_by("first_name", "last_name"),
        label=_("Pelanggan"),
        empty_label=_("Pilih pelanggan"),
    )
    groomer = forms.ModelChoiceField(
        queryset=User.groomers().order_by("first_name", "username"),
        label=_("Groomer"),
        required=False,
        empty_label=_("Belum ditentukan"),
    )

    allow_past = True

    field_order = ["customer", "service", "pet_name", "pet_type", "schedule", "groomer", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Booking dari meja kasir: hewan diantar sendiri, tanpa pin peta.
        for name in ("pet", "pickup", "return_trip", "address", "latitude", "longitude"):
            self.fields.pop(name)


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ["name", "pet_type", "price", "duration_minutes", "description", "is_active"]


class FinishForm(forms.Form):
    note = forms.CharField(max_length=255, required=False, label=_("Catatan hasil"))


class PetForm(forms.ModelForm):
    class Meta:
        model = Pet
        fields = ["name", "pet_type", "breed", "sex", "birth_date", "weight_kg", "notes", "photo"]
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "weight_kg": forms.NumberInput(attrs={"step": "0.1", "min": "0"}),
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "image"):
            clean_photo(photo)
        return photo

    def clean_birth_date(self):
        born = self.cleaned_data.get("birth_date")
        if born and born > timezone.localdate():
            raise forms.ValidationError(_("Tanggal lahir tidak boleh di masa depan."))
        return born


class CheckInForm(forms.Form):
    """Pemeriksaan singkat saat hewan tiba di toko; foto kondisi opsional."""

    weight_kg = forms.DecimalField(
        required=False, max_digits=5, decimal_places=2, min_value=0, label=_("Berat (kg)")
    )
    condition = forms.CharField(
        required=False, max_length=255, label=_("Kondisi saat datang"),
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": _("Mis. sehat, ada kutu, luka kecil di kaki kiri")}),
    )
    photo = forms.ImageField(required=False)

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        return clean_photo(photo) if photo else None


class StepForm(CameraPhotoForm):
    """Foto tiap tahap pengerjaan. Wajib/tidaknya foto ditentukan tahapnya (dicek di model)."""

    def __init__(self, *args, photo_required=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["photo"].required = photo_required


class RatingForm(forms.Form):
    stars = forms.TypedChoiceField(
        choices=[(n, n) for n in range(5, 0, -1)], coerce=int, label=_("Bintang"),
        error_messages={"required": _("Pilih jumlah bintang.")},
    )
    review = forms.CharField(required=False, max_length=255, label=_("Ulasan"))


ServiceStepFormSet = forms.inlineformset_factory(
    Service,
    ServiceStep,
    fields=["position", "name", "needs_photo"],
    extra=2,
    can_delete=True,
)
