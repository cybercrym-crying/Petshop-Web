from django.db import models
from django.contrib.auth.models import AbstractUser


class Role(models.TextChoices):
    # Role lama ADMIN/COURIR sudah tidak sesuai requirement — diganti sesuai
    # stakeholder di requirement gathering (Owner, Kasir, Staf Gudang, Groomer,
    # Pelanggan). Role "Admin"/"Dokter" lama sudah dihapus per catatan revisi.
    OWNER = "OWNER"
    KASIR = "KASIR"
    STAF_GUDANG = "STAF_GUDANG"
    GROOMER = "GROOMER"
    PELANGGAN = "PELANGGAN"


class User(AbstractUser):
    first_name = None
    last_name = None
    name = models.CharField(max_length=255, null=False, blank=False)
    role = models.CharField(max_length=20, choices=Role.choices, null=False)

    @property
    def isStaff(self):
        """Staff internal = semua role selain pelanggan."""
        return self.role != Role.PELANGGAN


class Customer(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="customerProfile"
    )
    name = models.CharField(max_length=255, null=False, blank=False)
    phoneNumber = models.CharField(max_length=20, null=False, blank=False)
    address = models.CharField(max_length=255, null=False, blank=False)

    def __str__(self):
        return self.name