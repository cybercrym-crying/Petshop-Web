from django import forms

from .models import CourierProfile


class CourierProfileForm(forms.ModelForm):
    class Meta:
        model = CourierProfile
        fields = ["vehicle", "plate_number", "service_area", "status"]
        widgets = {
            "vehicle": forms.TextInput(attrs={"class": "form-control"}),
            "plate_number": forms.TextInput(attrs={"class": "form-control"}),
            "service_area": forms.TextInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }
