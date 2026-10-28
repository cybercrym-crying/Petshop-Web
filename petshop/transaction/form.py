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
        labels = {
            "courier": "Kurir", "order_status": "Status pesanan", "payment_method": "Metode pembayaran",
            "payment_status": "Status pembayaran", "total_payment": "Total pembayaran",
        }

    def clean(self):
        pass


class OrderDetailForm(forms.ModelForm):

    class Meta:
        model = OrderDetail
        fields = ["transaction", "product", "quantity", "unit_price", "subtotal"]
        labels = {"transaction": "Transaksi", "product": "Produk", "quantity": "Jumlah", "unit_price": "Harga satuan"}
