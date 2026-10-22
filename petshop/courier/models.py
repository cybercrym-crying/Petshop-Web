from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel

TRAIL_FALLBACK_WINDOW = timedelta(hours=12)


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


# Lokasi GPS kurir dari Geolocation API (HTML5) di HP kurir. Satu baris per
# kiriman lokasi; jejak sebuah order = lokasi kurir antara shipped_at dan
# delivered_at order tersebut, jadi satu kiriman berlaku untuk semua paket
# yang sedang dibawa kurir itu.
class CourierLocation(models.Model):
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="locations",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy = models.PositiveIntegerField(
        "Akurasi (meter)", null=True, blank=True
    )
    recorded_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["recorded_at"]
        indexes = [models.Index(fields=["courier", "recorded_at"])]
        verbose_name = "lokasi kurir"
        verbose_name_plural = "lokasi kurir"

    def __str__(self):
        return f"{self.courier} @ {self.latitude},{self.longitude}"

    def as_point(self):
        return {
            "lat": float(self.latitude),
            "lng": float(self.longitude),
            "accuracy": self.accuracy,
            "at": self.recorded_at.isoformat(),
        }

    @classmethod
    def trail_for(cls, order, limit=300):
        """Jejak kurir selama order ini diantar (paling baru di akhir)."""
        if not order.courier_id:
            return []
        # Order lama (sebelum ada shipped_at) memakai jendela 12 jam terakhir.
        since = order.shipped_at or max(
            order.date, timezone.now() - TRAIL_FALLBACK_WINDOW
        )
        qs = cls.objects.filter(courier_id=order.courier_id, recorded_at__gte=since)
        if order.delivered_at:
            qs = qs.filter(recorded_at__lte=order.delivered_at)
        points = list(qs.order_by("-recorded_at")[:limit])
        points.reverse()
        return points
