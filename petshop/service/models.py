from django.db import models
from django.utils import timezone


class BookingStatus(models.TextChoices):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Service(models.Model):
    name = models.CharField(max_length=64, null=False, blank=False)
    price = models.PositiveBigIntegerField(null=False, blank=False)
    duration_minutes = models.PositiveIntegerField(help_text="Durasi dalam menit")


class Booking(models.Model):
    customer = models.ForeignKey("account.Customer", on_delete=models.CASCADE)
    pet = models.ForeignKey("account.Pet", on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    employee = models.ForeignKey("account.Employee", on_delete=models.PROTECT)
    booking_status = models.CharField(
        max_length=20, choices=BookingStatus.choices, default=BookingStatus.PENDING
    )
    datetime_booking = models.DateTimeField(default=timezone.now)
    datetime_service = models.DateTimeField()
    note = models.CharField(max_length=255, null=True, blank=True)


# Create your models here.
