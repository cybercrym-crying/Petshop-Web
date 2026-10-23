"""Validasi upload foto produk (ukuran & format)."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from product.form import MAX_PHOTO_SIZE, FormProduct
from product.models import Category


def image_file(fmt="PNG", name="foto.png", size=(10, 10)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "purple").save(buffer, fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{fmt.lower()}")


class ProductPhotoValidationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name=Category.FOOD)

    def form(self, photo):
        data = {
            "category": self.category.pk,
            "name": "Whiskas",
            "purchase_price": 1000,
            "selling_price": 2000,
            "stock": 1,
            "is_active": True,
        }
        return FormProduct(data, {"photo": photo})

    def test_png_is_accepted(self):
        self.assertTrue(self.form(image_file()).is_valid())

    def test_gif_is_rejected(self):
        form = self.form(image_file("GIF", "anim.gif"))
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)

    def test_oversized_photo_is_rejected(self):
        photo = image_file()
        photo.size = MAX_PHOTO_SIZE + 1
        form = self.form(photo)
        self.assertFalse(form.is_valid())
        self.assertIn("5 MB", str(form.errors["photo"]))


class ProductDescriptionTests(TestCase):
    def test_description_saved_and_shown_on_detail_page(self):
        from django.urls import reverse

        category = Category.objects.create(name=Category.FOOD)
        form = FormProduct(
            {
                "category": category.pk,
                "name": "Whiskas",
                "description": "Makanan kering kucing dewasa, 1,2 kg.",
                "purchase_price": 1000,
                "selling_price": 2000,
                "stock": 3,
                "is_active": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        r = self.client.get(reverse("customer:product_detail", args=[product.pk]))
        self.assertContains(r, "Makanan kering kucing dewasa, 1,2 kg.")
