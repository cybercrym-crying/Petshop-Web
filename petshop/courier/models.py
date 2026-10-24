from datetime import timedelta

from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel

TRAIL_FALLBACK_WINDOW = timedelta(hours=12)


class CourierStatus(models.TextChoices):
    ACTIVE = "AKTIF", _("Aktif")
    OFFLINE = "OFFLINE", _("Offline")
    BREAK = "ISTIRAHAT", _("Istirahat")


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
    # Kurir yang membawa kandang/boks hewan bisa ditugasi antar-jemput hewan grooming.
    can_carry_pets = models.BooleanField("Bisa antar-jemput hewan", default=False)
    # Foto wajah kurir: tampil di halaman lacak pelanggan dan dasbor admin.
    photo = models.ImageField(_("Foto kurir"), upload_to="couriers/%Y/%m", null=True, blank=True)

    def __str__(self):
        name = self.user.get_full_name() or self.user.username
        return f"{name} ({self.status})"

    class Meta:
        verbose_name = "profil kurir"
        verbose_name_plural = "profil kurir"


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
    def latest_for(cls, courier):
        return cls.objects.filter(courier=courier).order_by("-recorded_at").first()

    @classmethod
    def is_fresh(cls, courier):
        """GPS kurir dianggap hidup bila lokasi terakhir masuk dalam batas Pengaturan Toko."""
        from store.models import StoreSettings

        last = cls.latest_for(courier)
        limit = timedelta(seconds=StoreSettings.current().gps_stale_seconds)
        return bool(last and timezone.now() - last.recorded_at <= limit)

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


class RemittanceStatus(models.TextChoices):
    SUBMITTED = "MENUNGGU", _("Menunggu diterima kasir")
    RECEIVED = "DITERIMA", _("Diterima")


# Setoran uang COD dari kurir ke toko. Satu setoran mencakup beberapa order
# tunai yang sudah diserahkan (Order.remittance menunjuk ke sini).
class CashRemittance(models.Model):
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="remittances"
    )
    amount = models.PositiveBigIntegerField("Jumlah yang disetor")
    status = models.CharField(
        max_length=10, choices=RemittanceStatus.choices, default=RemittanceStatus.SUBMITTED, db_index=True
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    received_at = models.DateTimeField(null=True, blank=True)
    received_amount = models.PositiveBigIntegerField("Uang yang diterima kasir", null=True, blank=True)
    note = models.CharField("Catatan", max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = "setoran COD"
        verbose_name_plural = "setoran COD"

    def __str__(self):
        return f"Setoran #{self.pk} {self.courier} Rp {self.amount}"

    @property
    def difference(self):
        if self.received_amount is None:
            return 0
        return self.received_amount - self.amount

    @classmethod
    def submit(cls, courier):
        """Kurir menyetor semua uang COD yang belum disetor dalam satu setoran."""
        from django.db import transaction

        from common.exceptions import PetshopError
        from transaction.models import Order

        with transaction.atomic():
            orders = list(Order.cash_on_hand(courier).select_for_update())
            if not orders:
                raise PetshopError("Tidak ada uang COD yang perlu disetor.")
            remittance = cls.objects.create(
                courier=courier, amount=sum(o.cash_collected for o in orders)
            )
            Order.objects.filter(pk__in=[o.pk for o in orders]).update(remittance=remittance)
        return remittance

    def receive(self, cashier, received_amount, note=""):
        from common.exceptions import PetshopError

        if self.status != RemittanceStatus.SUBMITTED:
            raise PetshopError(f"Setoran #{self.pk} sudah diterima.")
        if received_amount is None or received_amount < 0:
            raise PetshopError("Isi jumlah uang yang benar-benar diterima.")
        if received_amount != self.amount and not note.strip():
            raise PetshopError("Jumlah berbeda dari tagihan: tulis catatan selisihnya.")
        self.status = RemittanceStatus.RECEIVED
        self.received_by = cashier
        self.received_at = timezone.now()
        self.received_amount = received_amount
        self.note = note.strip()[:255]
        self.save()
