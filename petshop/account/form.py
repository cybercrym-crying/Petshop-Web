from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class RegisterForm(forms.ModelForm):

    username = forms.CharField(max_length=255)
    name = forms.CharField(max_length=255)
    email = forms.EmailField()
    phoneNumber = forms.CharField(max_length=20)
    address = forms.CharField(max_length=255)
    password = forms.CharField(min_length=5, max_length=12, widget=forms.PasswordInput)
    passwordConfirm = forms.CharField(
        max_length=12, widget=forms.PasswordInput, label="Confirm Password"
    )

    class Meta:
        model = User
        fields = ["username", "name", "email", "password"]

    def clean(self):
        cleanedData = super().clean()
        password = cleanedData.get("password")
        passwordConfirm = cleanedData.get("passwordConfirm")
        if password and passwordConfirm and password != passwordConfirm:
            raise forms.ValidationError("Password harus sama.")
        return cleanedData


class LoginForm(forms.Form):
    username = forms.CharField(max_length=255)
    password = forms.CharField(max_length=12, widget=forms.PasswordInput)