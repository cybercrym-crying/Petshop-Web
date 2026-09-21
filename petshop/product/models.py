from django.db import models
from django.utils import timezone


class Category(models.Model):
    pass


class Product(models.Model):
    category = models.ForeignKey(Category, null=False, on_delete=models.PROTECT)
    name = models.CharField(max_length=255, null=False, blank=False)
    purchase_price = models.PositiveBigIntegerField(null=False, blank=False)
    selling_price = models.PositiveBigIntegerField(null=True, blank=True)
    stock = models.PositiveIntegerField(null=False, default=0)
    is_active = models.BooleanField(default=True)


class StockMutation(models.Model):
    product = models.ForeignKey(Product, null=False, on_delete=models.PROTECT)
    mutation_type = models.CharField(max_length=64, null=False, blank=False)
    quantity = models.IntegerField(null=False)
    date = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=255, default="", blank=True)


# Create your models here.
