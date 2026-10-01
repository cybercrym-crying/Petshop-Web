from django import forms
from .models import OrderDetail, Order
from product.models import Product


class OrderForm(forms.ModelForm):

    class Meta:
        model = Order
        fields = [
            "admin",
            "courir",
            "customer",
            "order_status",
            "payment_method",
            "payment_status",
            "total_payment",
        ]

    def clean(self):
        pass


class OrderDetailForm(forms.ModelForm):

    class Meta:
        model = OrderDetail
        fields = ["transaction", "product", "quantity", "subtotal"]
