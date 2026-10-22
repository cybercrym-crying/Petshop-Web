from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from .models import STAFF_ROLES, Customer, Role
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


class CustomerForm(forms.ModelForm):
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
        fields = ["phone_number", "address"]

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
    """Pendaftaran akun pelanggan dari situs (role otomatis CUSTOMER)."""

    name = forms.CharField(max_length=255, label="Nama lengkap")
    phone_number = forms.CharField(max_length=20, label="Nomor telepon")
    address = forms.CharField(max_length=255, label="Alamat")
    password1 = forms.CharField(widget=forms.PasswordInput, label="Kata sandi")
    password2 = forms.CharField(
        widget=forms.PasswordInput, label="Ulangi kata sandi"
    )

    field_order = ["name", "username", "phone_number", "address", "password1", "password2"]

    class Meta:
        model = Customer
        fields = ["username", "phone_number", "address"]
        labels = {"username": "Nama pengguna"}

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
