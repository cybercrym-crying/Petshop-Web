from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import ADMIN_ROLES, STAFF_ROLES, Approval, Customer, Role
from .phone import normalize_phone

User = get_user_model()


def _clean_phone(value):
    try:
        return normalize_phone(value)
    except ValueError as e:
        raise forms.ValidationError(str(e))


def _phone_taken_by_other_customer(phone, instance):
    others = User.customers().filter(phone_number=phone)
    if instance is not None and instance.pk:
        others = others.exclude(pk=instance.pk)
    return others.exists()


class PinMixin:
    """Titik peta (lat/lng) opsional di form pelanggan: diisi berdua atau dikosongkan berdua."""

    def clean(self):
        cleaned = super().clean()
        lat, lng = cleaned.get("latitude"), cleaned.get("longitude")
        if (lat is None) != (lng is None):
            self.add_error("latitude", "Titik peta tidak lengkap. Klik ulang lokasi di peta.")
        elif lat is not None and not (-90 <= lat <= 90 and -180 <= lng <= 180):
            self.add_error("latitude", "Titik peta tidak valid.")
        return cleaned


class CustomerForm(PinMixin, forms.ModelForm):
    """Data pelanggan (User role CUSTOMER) yang diisi admin.

    Nama pengguna & kata sandi opsional: kalau kosong, nama pengguna dibuat dari
    nomor HP dan akun belum bisa login sampai diberi kata sandi.
    """

    name = forms.CharField(max_length=255, label="Nama")
    phone_number = forms.CharField(max_length=20, label="Nomor telepon")
    address = forms.CharField(max_length=255, label="Alamat")
    username = forms.CharField(max_length=150, required=False, label="Nama pengguna")
    password = forms.CharField(
        widget=forms.PasswordInput, required=False, label="Kata sandi"
    )

    class Meta:
        model = Customer
        fields = ["phone_number", "address", "latitude", "longitude"]

    def clean_phone_number(self):
        phone = _clean_phone(self.cleaned_data["phone_number"])
        if _phone_taken_by_other_customer(phone, self.instance):
            raise forms.ValidationError("Nomor telepon sudah dipakai pelanggan lain.")
        return phone

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            return ""
        taken = User.objects.filter(username__iexact=username)
        if self.instance.pk:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("Nama pengguna sudah dipakai.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password

    def save(self, commit=True):
        customer = super().save(commit=False)
        customer.name = self.cleaned_data["name"]
        if self.cleaned_data.get("username"):
            customer.username = self.cleaned_data["username"]
        if self.cleaned_data.get("password"):
            customer.set_password(self.cleaned_data["password"])
        if commit:
            customer.save()
        return customer


class QuickCustomerForm(CustomerForm):
    """Pelanggan baru dari layar kasir / Buat Booking: tanpa akun login (nama pengguna dibuat dari
    nomor HP). Pelanggan bisa membuat kata sandi sendiri nanti lewat daftar di situs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["username"]
        del self.fields["password"]
        self.fields["phone_number"].label = "Nomor WhatsApp"


class EmployeeForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput, required=False, label="Kata sandi"
    )
    role = forms.ChoiceField(
        label="Peran",
        choices=[(code, Role(code).label) for code in STAFF_ROLES],
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "phone_number", "role"]
        labels = {
            "username": "Nama pengguna",
            "first_name": "Nama depan",
            "last_name": "Nama belakang",
            "phone_number": "Nomor telepon",
        }

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Hanya Super Admin yang boleh memberi peran Admin/Super Admin.
        if actor is not None and not actor.is_superadmin:
            own = self.instance.pk and self.instance.pk == actor.pk
            self.fields["role"].choices = [
                (code, label) for code, label in self.fields["role"].choices
                if code not in ADMIN_ROLES or (own and code == self.instance.role)
            ]

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("password"):
            self.add_error("password", "Kata sandi wajib diisi.")
        return cleaned

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if password:
            validate_password(password)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class RegisterForm(forms.ModelForm):
    """Pendaftaran akun pelanggan dari situs (role otomatis CUSTOMER).

    Alamat tidak diminta di sini: baru diisi (dengan titik peta) saat pelanggan memesan.
    """

    name = forms.CharField(max_length=255, label="Nama lengkap")
    phone_number = forms.CharField(max_length=20, label="Nomor telepon")
    password1 = forms.CharField(widget=forms.PasswordInput, label="Kata sandi")
    password2 = forms.CharField(
        widget=forms.PasswordInput, label="Ulangi kata sandi"
    )

    field_order = ["name", "username", "phone_number", "password1", "password2"]

    class Meta:
        model = Customer
        fields = ["username", "phone_number"]
        labels = {"username": "Nama pengguna"}
        error_messages = {"username": {"unique": "Nama pengguna sudah dipakai. Coba nama lain."}}

    def clean_phone_number(self):
        phone = _clean_phone(self.cleaned_data["phone_number"])
        if _phone_taken_by_other_customer(phone, None):
            raise forms.ValidationError(
                "Nomor telepon sudah terdaftar. Silakan masuk atau hubungi admin."
            )
        return phone

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Kata sandi tidak sama.")
        elif p1:
            try:
                validate_password(p1)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return cleaned

    def save(self, commit=True):
        customer = super().save(commit=False)
        customer.name = self.cleaned_data["name"]
        customer.set_password(self.cleaned_data["password1"])
        if commit:
            customer.save()
        return customer


class LoginForm(forms.Form):

    username = forms.CharField(max_length=255, label="Nama pengguna")
    password = forms.CharField(widget=forms.PasswordInput, label="Kata sandi")


class ProfileForm(PinMixin, forms.ModelForm):
    """Pelanggan mengubah data akunnya sendiri (nama pengguna & peran tidak bisa diubah)."""

    name = forms.CharField(max_length=255, label="Nama lengkap")
    phone_number = forms.CharField(max_length=20, label="Nomor WhatsApp")
    address = forms.CharField(
        max_length=255,
        required=False,
        label="Alamat utama",
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Dipakai sebagai isian awal saat checkout.",
    )

    class Meta:
        model = Customer
        fields = ["email", "phone_number", "address", "latitude", "longitude"]
        labels = {"email": "Email (opsional)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].initial = self.instance.name
        self.order_fields(["name", "phone_number", "email", "address"])

    def clean_phone_number(self):
        phone = _clean_phone(self.cleaned_data["phone_number"])
        if _phone_taken_by_other_customer(phone, self.instance):
            raise forms.ValidationError("Nomor telepon sudah dipakai pelanggan lain.")
        return phone

    def save(self, commit=True):
        user = super().save(commit=False)
        user.name = self.cleaned_data["name"]
        if commit:
            user.save()
        return user


class ProfilePhotoForm(forms.Form):
    """Foto profil pelanggan: unggah baru (JPG/PNG/WEBP, maks. 10 MB) atau hapus."""

    photo = forms.ImageField(
        required=False,
        error_messages={"invalid_image": "File harus berupa foto (JPG, PNG, atau WEBP)."},
    )
    remove = forms.BooleanField(required=False)

    def clean_photo(self):
        from common.photos import clean_photo

        photo = self.cleaned_data.get("photo")
        return clean_photo(photo) if photo else None

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("photo") and not cleaned.get("remove") and not self.errors:
            raise forms.ValidationError("Pilih foto terlebih dahulu.")
        return cleaned

    def save(self, user):
        old = user.photo.name if user.photo else ""
        user.photo = self.cleaned_data.get("photo") or None
        user.save(update_fields=["photo"])
        if old and old != (user.photo.name if user.photo else ""):
            user.photo.storage.delete(old)
        return user


class StaffRegisterForm(forms.ModelForm):
    """Calon kurir mendaftar sendiri; akun aktif setelah disetujui admin.

    Halaman ini khusus kurir (tanpa pilihan peran). Kasir dan groomer tidak bisa mendaftar
    sendiri: akunnya dibuat Admin/Super Admin.
    """

    name = forms.CharField(max_length=255, label="Nama lengkap")
    phone_number = forms.CharField(max_length=20, label="Nomor WhatsApp")
    vehicle = forms.CharField(
        max_length=50, label="Kendaraan", error_messages={"required": "Wajib diisi untuk kurir."}
    )
    plate_number = forms.CharField(
        max_length=20, label="Nomor polisi", error_messages={"required": "Wajib diisi untuk kurir."}
    )
    password1 = forms.CharField(widget=forms.PasswordInput, label="Kata sandi")
    password2 = forms.CharField(widget=forms.PasswordInput, label="Ulangi kata sandi")

    field_order = [
        "name", "username", "phone_number",
        "vehicle", "plate_number", "password1", "password2",
    ]

    class Meta:
        model = User
        fields = ["username"]
        labels = {"username": "Nama pengguna"}
        error_messages = {"username": {"unique": "Nama pengguna sudah dipakai. Coba nama lain."}}

    def clean_phone_number(self):
        return _clean_phone(self.cleaned_data["phone_number"])

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Kata sandi tidak sama.")
        elif p1:
            try:
                validate_password(p1)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return cleaned

    def save(self, commit=True):
        from courier.models import CourierProfile

        user = super().save(commit=False)
        user.name = self.cleaned_data["name"]
        user.phone_number = self.cleaned_data["phone_number"]
        user.role = Role.COURIER
        user.approval = Approval.PENDING
        user.is_active = False
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            CourierProfile.objects.update_or_create(
                user=user,
                defaults={
                    "vehicle": self.cleaned_data["vehicle"].strip(),
                    "plate_number": self.cleaned_data["plate_number"].strip().upper(),
                },
            )
        return user
