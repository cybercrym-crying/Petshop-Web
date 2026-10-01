from django.db import models
from django.utils import timezone
from django.db import models
from django.conf import settings
from product.models import Product
from account.models import Customer, User


class PaymentMethod(models.TextChoices):
    CASH = "CASH"
    TRANSFER = "TRANSFER"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class OrderStatus(models.TextChoices):
    PENDING = "PENDING"
    ON_DELIVERY = "ON DELIVERY"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Order(models.Model):
    admin = models.ForeignKey("account.User", on_delete=models.PROTECT)
    courir = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, related_name="orders_as_cashier"
    )
    customer = models.ForeignKey(
        "account.Customer", on_delete=models.PROTECT, related_name="orders_as_courir"
    )
    order_status = models.CharField(
        max_length=20, choices=OrderStatus.choices, null=False, blank=False
    )
    payment_method = models.CharField(max_length=50, choices=PaymentMethod.choices)
    payment_status = models.CharField(
        max_length=50, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    total_payment = models.PositiveBigIntegerField(default=0)
    date = models.DateTimeField(default=timezone.now)


class OrderDetail(models.Model):
    transaction = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="details"
    )

    product = models.ForeignKey(
        "product.Product", on_delete=models.PROTECT, null=True, blank=True
    )

    quantity = models.PositiveIntegerField()
    subtotal = models.PositiveBigIntegerField()


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ["cart", "product"]

    @property
    def subtotal(self):
        return (self.product.selling_price or 0) * self.quantity


# Create your models here.
