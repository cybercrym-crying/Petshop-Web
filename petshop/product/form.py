from django import forms
from .models import Category


class FormProduct(forms.Form):
    category = forms.ModelChoiceField(queryset=Category.objects.all())
    name = forms.CharField(max_length=64, strip=True)
    purchase_price = forms.IntegerField(min_value=0)
    selling_price = forms.IntegerField(required=False, min_value=0)
    stock = forms.IntegerField(min_value=0)
    is_active = forms.BooleanField()
    image = forms.ImageField(required=False)
