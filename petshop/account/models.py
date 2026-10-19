from urllib.parse import quote

from django.db import models
from django.contrib.auth.models import AbstractUser


class Role(models.TextChoices):
    ADMIN = "ADMIN"
    COURIER = "COURIER"


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, null=False)
    phone_number = models.CharField(max_length=20)

    @property
    def dashboard_url_name(self):
        return {
            Role.ADMIN: "staff_admin_dashboard",
            Role.COURIER: "courier:dashboard",
        }.get(self.role, "customer:home")


class Customer(models.Model):
    name = models.CharField(max_length=255, null=False, blank=False)
    phone_number = models.CharField(
        max_length=20, null=False, blank=False, unique=True
    )
    address = models.CharField(max_length=255, null=False, blank=False)

    @property
    def whatsapp_url(self):
        number = self.phone_number
        number = "62" + number[1:] if number.startswith("0") else number
        return f"https://wa.me/{number}"

    @property
    def maps_url(self):
        return f"https://www.google.com/maps/search/?api=1&query={quote(self.address)}"

    def __str__(self):
        return f"{self.name} ({self.phone_number})"
