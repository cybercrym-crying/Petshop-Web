from django import forms

MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB, cukup untuk foto kamera HP
ALLOWED_PHOTO_FORMATS = {"JPEG", "PNG", "WEBP"}


def clean_photo(photo):
    """Validasi foto dari kamera/galeri: ukuran & format gambar asli (bukan sekadar ekstensi)."""
    if photo.size > MAX_PHOTO_SIZE:
        raise forms.ValidationError("Ukuran foto maksimal 10 MB.")
    image_format = getattr(getattr(photo, "image", None), "format", None)
    if image_format not in ALLOWED_PHOTO_FORMATS:
        raise forms.ValidationError("Format foto harus JPG, PNG, atau WEBP.")
    return photo


class CameraPhotoForm(forms.Form):
    """Satu foto wajib (diambil lewat static/js/camera.js) + catatan opsional + titik GPS saat memotret."""

    photo = forms.ImageField(
        error_messages={
            "required": "Ambil foto terlebih dahulu.",
            "invalid_image": "File harus berupa foto (JPG, PNG, atau WEBP).",
        },
    )
    note = forms.CharField(required=False, max_length=255)
    latitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = forms.DecimalField(required=False, max_digits=9, decimal_places=6, min_value=-180, max_value=180)

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        return clean_photo(photo) if photo else None
