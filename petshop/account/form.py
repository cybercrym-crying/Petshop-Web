from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class RegisterForm(forms.ModelForm):
    username = forms.CharField(max_length=255)
    name = forms.CharField(max_length=255)
    email = forms.EmailField()
    phone_number = forms.CharField(max_length=12)
    password = forms.CharField(min_length=5, max_length=12, widget=forms.PasswordInput)
    password_confirm = forms.CharField(
        max_length=12, widget=forms.PasswordInput, label="Confirm Password"
    )

    class Meta:
        model = User
        fields = ["username", "email", "password", "password_confirm"]

    def clean(self):
        cleaned_data = super().clean()
        password = self.cleaned_data.get("password")
        password_confirm = self.cleaned_data.get("password_confirm")
        email = self.cleaned_data.get("email")
        if password and password_confirm and password_confirm != password:
            raise forms.ValidationError("Password Must be match")
        return cleaned_data


class LoginForm(forms.Form):
    username = forms.CharField(max_length=255)
    password = forms.CharField(max_length=12, widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["username", "password"]

    def clean(self):
        cleaned_data = super().clean()
        password = self.cleaned_data.get("password")
        return cleaned_data
