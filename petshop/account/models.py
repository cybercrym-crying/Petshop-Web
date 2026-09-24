from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.functions.text import Length


class Role(models.TextChoices):
    ADMIN = "ADMIN"
    COURIR = "COURIR"


class User(AbstractUser):
    first_name = None
    last_name = None
    name = models.CharField(max_length=255, null=False, blank=False)
    role = models.CharField(max_length=20, choices=Role.choices, null=False)


class Customer(models.Model):
    name = models.CharField(max_length=255, null=False, blank=False)
    phone_number = models.CharField(max_length=20, null=False, blank=False)
    address = models.CharField(max_length=255, null=False, blank=False)
