from django import forms
from django.contrib.auth import get_user_model
from .models import Customer
from .phone import normalize_phone
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class CustomerForm(forms.ModelForm):
    name = forms.CharField(max_length=255, label="Nama")
    phone_number = forms.CharField(max_length=20, label="Nomor telepon")
    address = forms.CharField(max_length=255, label="Alamat")

    class Meta:
        model = Customer
        fields = ["name", "phone_number", "address"]

    def clean_phone_number(self):
        try:
            return normalize_phone(self.cleaned_data["phone_number"])
        except ValueError as e:
            raise forms.ValidationError(str(e))


class EmployeeForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput, required=False, label="Kata sandi"
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "phone_number", "role"]
        labels = {
            "username": "Nama pengguna",
            "first_name": "Nama depan",
            "last_name": "Nama belakang",
            "phone_number": "Nomor telepon",
            "role": "Peran",
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


class LoginForm(forms.Form):

    username = forms.CharField(max_length=255, label="Nama pengguna")
    password = forms.CharField(widget=forms.PasswordInput, label="Kata sandi")
