from django.db import models
from django.utils import timezone


class Category(models.Model):
    FOOD = "FOOD"
    EQUIPMENT = "EQUIPMENT"
    ACCESSORIES = "ACCESSORIES"

    CATEGORY_CHOICES = [
        (FOOD, "Food"),
        (EQUIPMENT, "Equipment"),
        (ACCESSORIES, "Accessories"),
    ]

    name = models.CharField(max_length=64, choices=CATEGORY_CHOICES, unique=True)

    def __str__(self):
        return self.get_name_display()


class MutationType(models.TextChoices):
    IN = "IN", "Stok Masuk"
    OUT = "OUT", "Stok Keluar"


class Product(models.Model):
    category = models.ForeignKey(Category, null=False, on_delete=models.PROTECT)
    name = models.CharField(max_length=255, null=False, blank=False)
    purchase_price = models.PositiveBigIntegerField(null=False, blank=False)
    selling_price = models.PositiveBigIntegerField(null=True, blank=True)
    stock = models.PositiveIntegerField(null=False, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    photo = models.ImageField(upload_to="products", null=True, blank=True)

    @property
    def isSellable(self):
        return self.is_active and self.selling_price is not None

    def __str__(self):
        return self.name


class StockMutation(models.Model):
    product = models.ForeignKey(
        Product, null=False, on_delete=models.PROTECT, related_name="mutations"
    )
    mutationType = models.CharField(
        max_length=8, choices=MutationType.choices, null=False
    )
    quantity = models.PositiveIntegerField(null=False)
    date = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=255, default="", blank=True)
    createdBy = models.ForeignKey(
        "account.User", null=True, blank=True, on_delete=models.SET_NULL
    )

    def __str__(self):
        return f"{self.product.name} {self.mutationType} {self.quantity}"
