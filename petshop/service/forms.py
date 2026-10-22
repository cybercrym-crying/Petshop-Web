from datetime import time, timedelta

from django import forms
from django.utils import timezone

from account.models import Customer, User
from product.models import PetType

from .models import Service

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
        label="Layanan",
        empty_label="Pilih layanan",
    )
    pet_name = forms.CharField(max_length=60, label="Nama hewan")
    pet_type = forms.ChoiceField(choices=PET_CHOICES, label="Jenis hewan")
    schedule = forms.DateTimeField(
        label="Jadwal datang",
        input_formats=[DATETIME_LOCAL, "%Y-%m-%d %H:%M"],
        widget=_schedule_widget(),
    )
    note = forms.CharField(
        max_length=255,
        required=False,
        label="Catatan",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Opsional, mis. kulit sensitif / galak saat potong kuku"}),
    )

    allow_past = False

    def clean_schedule(self):
        schedule = self.cleaned_data["schedule"]
        local = timezone.localtime(schedule)
        now = timezone.localtime()
        if not self.allow_past and schedule < now:
            raise forms.ValidationError("Jadwal harus setelah waktu sekarang.")
        if self.allow_past and local.date() < now.date():
            raise forms.ValidationError("Jadwal tidak boleh di hari yang sudah lewat.")
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
        service, pet = cleaned.get("service"), cleaned.get("pet_type")
        if service and pet and not service.suits(pet):
            self.add_error(
                "service",
                f"Layanan ini khusus {service.get_pet_type_display().lower()}.",
            )
        return cleaned


class StaffBookingForm(BookingForm):
    """Booking yang dibuat admin/kasir untuk pelanggan yang datang langsung."""

    customer = forms.ModelChoiceField(
        queryset=Customer.objects.order_by("first_name", "last_name"),
        label="Pelanggan",
        empty_label="Pilih pelanggan",
    )
    groomer = forms.ModelChoiceField(
        queryset=User.groomers().order_by("first_name", "username"),
        label="Groomer",
        required=False,
        empty_label="Belum ditentukan",
    )

    allow_past = True

    field_order = ["customer", "service", "pet_name", "pet_type", "schedule", "groomer", "note"]


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ["name", "pet_type", "price", "duration_minutes", "description", "is_active"]


class FinishForm(forms.Form):
    note = forms.CharField(max_length=255, required=False, label="Catatan hasil")
