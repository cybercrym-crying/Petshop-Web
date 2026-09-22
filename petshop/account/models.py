from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.functions.text import Length


class Role(models.TextChoices):
    OWNER = "OWNER"
    CASHIER = "CASHIER"
    WAREHOUSE = "WAREHOUSE"
    SERVICE = "SERVICE"


class Animal(models.TextChoices):
    DOG = "DOG"
    CAT = "CAT"
    RABBIT = "RABBIT"


class User(AbstractUser):
    first_name = None
    last_name = None


class Account(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, null=False)
    phone_number = models.CharField(max_length=12, null=False)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name}"


class Employee(Account):
    role = models.CharField(max_length=20, choices=Role.choices, null=False)


class Customer(Account):
    pass


class Pet(models.Model):
    owner = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=64, null=False, blank=False)
    animal_type = models.CharField(
        max_length=12, null=False, blank=False, choices=Animal.choices
    )
    breed = models.CharField(max_length=64, null=False, blank=False)
    medical_history = models.CharField(max_length=64, default="", blank=True)
