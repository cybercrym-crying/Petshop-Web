from django import forms
from .models import Category, Product, StockMutation, MutationType


class FormProduct(forms.ModelForm):

    class Meta:
        model = Product
        fields = [
            "category",
            "name",
            "purchase_price",
            "selling_price",
            "stock",
            "is_active",
            "photo",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stock"].help_text = (
            "Stok awal saat produk pertama kali ditambahkan"
        )
        # Stok hanya diisi saat produk baru dibuat.
        # Perubahan stok sesudahnya wajib lewat StockMutation supaya tercatat.
        if self.instance.pk:
            self.fields["stock"].disabled = True

    def clean(self):
        cleaned_data = super().clean()
        purchase_price = cleaned_data.get("purchase_price")
        selling_price = cleaned_data.get("selling_price")
        if (
            purchase_price is not None
            and selling_price is not None
            and selling_price < purchase_price
        ):
            self.add_error(
                "selling_price", "Harga jual tidak boleh lebih rendah dari harga beli."
            )
        return cleaned_data


class SellingPriceForm(forms.ModelForm):
    # Dipakai Owner untuk set/ubah harga jual produk

    class Meta:
        model = Product
        fields = ["selling_price"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["selling_price"].widget.attrs["class"] = "dark-input"

    def clean_selling_price(self):
        sellingPrice = self.cleaned_data.get("selling_price")
        if (
            sellingPrice is not None
            and sellingPrice < self.instance.purchase_price
        ):
            raise forms.ValidationError(
                "Harga jual tidak boleh lebih rendah dari harga beli."
            )
        return sellingPrice


class StockMutationForm(forms.ModelForm):
    # Dipakai Staf Gudang untuk mencatat stok masuk/keluar.

    quantity = forms.IntegerField(min_value=1)

    class Meta:
        model = StockMutation
        fields = ["product", "mutationType", "quantity", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "dark-input"

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
