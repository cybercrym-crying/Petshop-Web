from django import forms
from .models import OrderDetail, Order


class OrderForm(forms.ModelForm):

    class Meta:
        model = Order
        fields = [
            "admin",
            "courier",
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
        fields = ["transaction", "product", "quantity", "unit_price", "subtotal"]
