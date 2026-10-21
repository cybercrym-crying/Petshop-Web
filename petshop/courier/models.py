from django.conf import settings
from django.db import models
from common.models import TimeStampedModel


class CourierStatus(models.TextChoices):
    ACTIVE = "AKTIF", "Aktif"
    OFFLINE = "OFFLINE", "Offline"
    BREAK = "ISTIRAHAT", "Istirahat"


class CourierProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="courier_profile",
    )
    vehicle = models.CharField(max_length=50, blank=True, default="")
    plate_number = models.CharField(max_length=20, blank=True, default="")
    service_area = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=CourierStatus.choices,
        default=CourierStatus.ACTIVE,
    )

    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f"{name} ({self.status})"
