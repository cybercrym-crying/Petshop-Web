from django.db import models
from django.utils import timezone


class Category(models.Model):
    FOOD = "FOOD"
    EQUIPMENT = "EQUIPMENT"
    ACCESSORIES = "ACCESSORIES"


class MutationType(models.TextChoices):
    IN = "IN"
    OUT = "OUT"


class Product(models.Model):
    category = models.ForeignKey(Category, null=False, on_delete=models.PROTECT)
    name = models.CharField(max_length=255, null=False, blank=False)
    purchase_price = models.PositiveBigIntegerField(null=False, blank=False)
    selling_price = models.PositiveBigIntegerField(null=True, blank=True)
    stock = models.PositiveIntegerField(null=False, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    image = models.ImageField(upload_to="products", null=True, blank=True)


class StockMutation(models.Model):
    product = models.ForeignKey(Product, null=False, on_delete=models.PROTECT)
    mutation_type = models.CharField(max_length=64, null=False, blank=False)
    quantity = models.IntegerField(null=False)
    date = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=255, default="", blank=True)


# Create your models here.
