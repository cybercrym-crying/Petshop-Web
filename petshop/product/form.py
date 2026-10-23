from django import forms
from .models import MutationType, PetType, Product, ProductCondition, StockMutation


MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_PHOTO_FORMATS = {"JPEG", "PNG", "WEBP"}


class FormProduct(forms.ModelForm):

    class Meta:
        model = Product
        fields = [
            "category",
            "name",
            "sku",
            "description",
            "purchase_price",
            "selling_price",
            "stock",
            "pet_type",
            "condition",
            "is_active",
            "photo",
        ]
        labels = {
            "category": "Kategori",
            "name": "Nama produk",
            "sku": "Kode barang (SKU/barcode)",
            "description": "Deskripsi",
            "purchase_price": "Harga beli",
            "selling_price": "Harga jual",
            "stock": "Stok",
            "pet_type": "Tipe hewan",
            "condition": "Kondisi",
            "is_active": "Status aktif",
            "photo": "Foto produk",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stock"].help_text = (
            "Stok awal saat produk pertama kali ditambahkan"
        )
        # Hewan tujuan & kondisi opsional di form: kosong = SEMUA / BARU (bawaan model).
        self.fields["pet_type"].required = False
        self.fields["condition"].required = False
        # Stok hanya diisi saat produk baru dibuat.
        # Perubahan stok sesudahnya wajib lewat StockMutation supaya tercatat.
        if self.instance.pk:
            self.fields["stock"].disabled = True

    def clean_sku(self):
        sku = "".join((self.cleaned_data.get("sku") or "").split()).upper()
        if not sku:
            return None
        clash = Product.objects.filter(sku__iexact=sku).exclude(pk=self.instance.pk).first()
        if clash:
            raise forms.ValidationError(f"Kode {sku} sudah dipakai produk '{clash.name}'.")
        return sku

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        # Hanya file yang baru diunggah yang diperiksa (foto lama tidak punya .image).
        image = getattr(photo, "image", None)
        if photo and image is not None:
            if photo.size > MAX_PHOTO_SIZE:
                raise forms.ValidationError("Ukuran foto maksimal 5 MB.")
            if image.format not in ALLOWED_PHOTO_FORMATS:
                raise forms.ValidationError("Format foto harus JPG, PNG, atau WEBP.")
        return photo

    def clean_pet_type(self):
        return self.cleaned_data.get("pet_type") or PetType.ALL

    def clean_condition(self):
        return self.cleaned_data.get("condition") or ProductCondition.NEW

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
        labels = {"selling_price": "Harga jual"}

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

    quantity = forms.IntegerField(min_value=1, label="Jumlah")

    class Meta:
        model = StockMutation
        fields = ["product", "mutationType", "quantity", "note"]
        labels = {
            "product": "Produk",
            "mutationType": "Jenis mutasi",
            "quantity": "Jumlah",
            "note": "Catatan",
        }

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
