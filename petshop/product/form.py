from django import forms
from .models import Category, Product, StockMutation, MutationType


class FormProduct(forms.ModelForm):

    class Meta:
        model = Product
        fields = [
            "category",
            "name",
            "purchasePrice",
            "stock",
            "isActive",
            "image",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stock"].help_text = "Stok awal saat produk pertama kali ditambahkan"


class SellingPriceForm(forms.ModelForm):
    #Dipakai Owner untuk set/ubah harga jual produk

    class Meta:
        model = Product
        fields = ["sellingPrice"]


class StockMutationForm(forms.ModelForm):
    #Dipakai Staf Gudang untuk mencatat stok masuk/keluar.

    class Meta:
        model = StockMutation
        fields = ["product", "mutationType", "quantity", "note"]

    def clean(self):
        cleanedData = super().clean()
        mutationType = cleanedData.get("mutationType")
        quantity = cleanedData.get("quantity")
        product = cleanedData.get("product")
        if mutationType == MutationType.OUT and product and quantity:
            if quantity > product.stock:
                raise forms.ValidationError(
                    f"Stok tidak cukup. Stok saat ini: {product.stock}"
                )
        return cleanedData