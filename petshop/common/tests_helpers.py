"""Alat bantu tes bersama (bukan modul tes, jadi tidak dijalankan test runner)."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def tiny_photo(name="foto.jpg", color="#8c73c2"):
    """Foto JPEG kecil yang lolos validasi clean_photo (format gambar asli)."""
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), color).save(buf, "JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")
