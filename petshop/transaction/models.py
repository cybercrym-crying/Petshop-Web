from django.db import models
from django.utils import timezone


class PaymentMethod(models.TextChoices):
    CASH = "CASH"
    TRANSFER = "TRANSFER"
    DEBIT = "DEBIT"
    EWALLET = "EWALLET"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Transaction(models.Model):
    cashier = models.ForeignKey("account.Employee", on_delete=models.PROTECT)

    date = models.DateTimeField(default=timezone.now)
    total_payment = models.PositiveBigIntegerField(default=0)

    payment_method = models.CharField(max_length=50, choices=PaymentMethod.choices)
    payment_status = models.CharField(
        max_length=50, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )


class TransactionDetail(models.Model):
    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name="details"
    )

    product = models.ForeignKey(
        "product.Product", on_delete=models.PROTECT, null=True, blank=True
    )
    booking = models.ForeignKey(
        "service.Booking", on_delete=models.PROTECT, null=True, blank=True
    )

    quantity = models.PositiveIntegerField()
    subtotal = models.PositiveBigIntegerField()


# Create your models here.
