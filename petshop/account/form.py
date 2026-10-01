from django import forms
from django.contrib.auth import get_user_model
from django.utils import choices
from .models import Role, Customer
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class CustomerForm(forms.ModelForm):
    name = forms.CharField(max_length=255)
    phone_number = forms.CharField(max_length=20)
    address = forms.CharField(max_length=255)

    class Meta:
        model = Customer
        fields = ["name", "phone_number", "address"]


class EmployeeForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "phone_number", "role"]

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk and not cleaned.get("password"):
            self.add_error("password", "Password must be fill.")
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

    username = forms.CharField(max_length=255)
    password = forms.CharField(widget=forms.PasswordInput)
