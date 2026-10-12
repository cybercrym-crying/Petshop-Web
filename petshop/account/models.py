from django.db import models
from django.contrib.auth.models import AbstractUser


class Role(models.TextChoices):
    ADMIN = "ADMIN"
    COURIR = "COURIR"


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, null=False)
    phone_number = models.CharField(max_length=20)


class Customer(models.Model):
    name = models.CharField(max_length=255, null=False, blank=False)
    phone_number = models.CharField(max_length=20, null=False, blank=False)
    address = models.CharField(max_length=255, null=False, blank=False)

    def __str__(self):
        return f"{self.name}" f"{self.phone_number}" f"{self.address}"
