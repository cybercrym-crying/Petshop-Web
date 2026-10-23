from django import forms
from django.utils.translation import gettext_lazy as _

from common.photos import clean_photo

from .models import BankAccount, Complaint, ComplaintStatus, StoreSettings


class StoreSettingsForm(forms.ModelForm):
    class Meta:
        model = StoreSettings
        fields = [
            "name", "address", "latitude", "longitude", "open_hour", "close_hour",
            "whatsapp", "email",
            "shipping_base_fee", "shipping_base_km", "shipping_per_km", "max_delivery_km",
            "pickup_base_fee", "pickup_base_km", "pickup_per_km",
            "max_packages_per_courier", "payment_deadline_hours", "gps_stale_seconds",
            "grooming_reminder_days",
            "tax_percent", "cashier_discount_limit", "return_days", "qris_image", "receipt_footer",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "latitude": forms.NumberInput(attrs={"step": "0.000001", "data-map-lat": ""}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001", "data-map-lng": ""}),
            "qris_image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        # Pengaturan kasir boleh dikosongkan: nilai yang tersimpan tetap dipakai.
        for name in self.KEEP_WHEN_EMPTY:
            self.fields[name].required = False

    KEEP_WHEN_EMPTY = ("tax_percent", "cashier_discount_limit", "return_days")

    def _keep(self, name):
        value = self.cleaned_data.get(name)
        return getattr(self.instance, name) if value is None else value

    def clean_cashier_discount_limit(self):
        return self._keep("cashier_discount_limit")

    def clean_return_days(self):
        return self._keep("return_days")

    def clean_whatsapp(self):
        digits = "".join(ch for ch in self.cleaned_data["whatsapp"] if ch.isdigit())
        if digits.startswith("0"):
            digits = "62" + digits[1:]
        if not digits.startswith("62") or not 10 <= len(digits) <= 15:
            raise forms.ValidationError(_("Gunakan nomor Indonesia, contoh 081234567890 atau 6281234567890."))
        return digits

    def clean_qris_image(self):
        image = self.cleaned_data.get("qris_image")
        if image and hasattr(image, "image"):
            clean_photo(image)
        return image

    def clean_tax_percent(self):
        value = self._keep("tax_percent")
        if value < 0 or value > 100:
            raise forms.ValidationError(_("Pajak harus antara 0 dan 100 persen."))
        return value

    def clean(self):
        data = super().clean()
        lat, lng = data.get("latitude"), data.get("longitude")
        if lat is not None and not -90 <= lat <= 90:
            self.add_error("latitude", _("Latitude harus di antara -90 dan 90."))
        if lng is not None and not -180 <= lng <= 180:
            self.add_error("longitude", _("Longitude harus di antara -180 dan 180."))
        open_hour, close_hour = data.get("open_hour"), data.get("close_hour")
        if open_hour is not None and close_hour is not None:
            if not (0 <= open_hour < close_hour <= 24):
                self.add_error("close_hour", _("Jam tutup harus setelah jam buka (0–24)."))
        if data.get("payment_deadline_hours") == 0:
            self.add_error("payment_deadline_hours", _("Minimal 1 jam."))
        if data.get("max_packages_per_courier") == 0:
            self.add_error("max_packages_per_courier", _("Minimal 1 paket."))
        return data


class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ["bank", "number", "holder", "is_active"]
        widgets = {
            "bank": forms.TextInput(attrs={"class": "form-control", "placeholder": _("BCA")}),
            "number": forms.TextInput(attrs={"class": "form-control", "inputmode": "numeric"}),
            "holder": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


BankAccountFormSet = forms.modelformset_factory(
    BankAccount, form=BankAccountForm, extra=1, can_delete=True
)


class ComplaintForm(forms.ModelForm):
    """Komplain pelanggan: pilih pesanan/booking terkait (milik sendiri), foto opsional."""

    class Meta:
        model = Complaint
        fields = ["category", "order", "booking", "message", "photo"]
        widgets = {"message": forms.Textarea(attrs={"rows": 4, "placeholder": _("Ceritakan masalahnya sejelas mungkin.")})}
        labels = {"order": _("Pesanan terkait"), "booking": _("Booking terkait")}

    def __init__(self, *args, customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        from service.models import ServiceBooking
        from transaction.models import Order

        self.fields["order"].queryset = (
            Order.objects.filter(customer=customer).order_by("-date") if customer else Order.objects.none()
        )
        self.fields["booking"].queryset = (
            ServiceBooking.objects.filter(customer=customer).select_related("service").order_by("-schedule")
            if customer else ServiceBooking.objects.none()
        )
        self.fields["order"].label_from_instance = lambda o: f"#{o.pk} · {o.date:%d %b %Y} · {o.get_order_status_display()}"
        self.fields["booking"].label_from_instance = lambda b: f"#{b.pk} · {b.service.name} · {b.pet_name}"
        self.fields["order"].empty_label = _("Tidak terkait pesanan")
        self.fields["booking"].empty_label = _("Tidak terkait booking")

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "image"):
            clean_photo(photo)
        return photo


class ComplaintResponseForm(forms.Form):
    status = forms.ChoiceField(choices=ComplaintStatus.choices, label=_("Status"))
    response = forms.CharField(
        required=False, max_length=1000, label=_("Balasan ke pelanggan"),
        widget=forms.Textarea(attrs={"rows": 4}),
    )
