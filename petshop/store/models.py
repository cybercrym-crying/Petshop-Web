from django.utils.translation import gettext_lazy as _
import math
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel

# Titik awal bawaan (pusat Balikpapan) sampai admin mengisi lokasi toko sendiri.
DEFAULT_LAT = Decimal("-1.265400")
DEFAULT_LNG = Decimal("116.831200")
EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1, lng1, lat2, lng2):
    """Jarak garis lurus (km) antara dua titik di bumi."""
    lat1, lng1, lat2, lng2 = (math.radians(float(v)) for v in (lat1, lng1, lat2, lng2))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def tiered_fee(distance_km, base_fee, base_km, per_km):
    """Tarif = biaya dasar untuk `base_km` pertama + per km berikutnya (dibulatkan ke atas)."""
    extra_km = max(0.0, float(distance_km) - float(base_km))
    return int(base_fee + math.ceil(extra_km) * per_km)


# OOP: ENKAPSULASI - satu baris pengaturan toko (singleton). Data yang sering
# berubah (alamat, rekening, tarif) diatur admin dari halaman, bukan di kode.
class StoreSettings(models.Model):
    name = models.CharField("Nama toko", max_length=120, default="Seelly Petshop")
    address = models.CharField("Alamat toko", max_length=255, default="Balikpapan, Kalimantan Timur")
    latitude = models.DecimalField("Latitude", max_digits=9, decimal_places=6, default=DEFAULT_LAT)
    longitude = models.DecimalField("Longitude", max_digits=9, decimal_places=6, default=DEFAULT_LNG)
    open_hour = models.PositiveSmallIntegerField("Jam buka", default=8)
    close_hour = models.PositiveSmallIntegerField("Jam tutup", default=20)
    whatsapp = models.CharField(
        "Nomor WhatsApp admin", max_length=20, default="6281356703075",
        help_text="Format internasional tanpa +, contoh 6281234567890.",
    )
    email = models.EmailField("Email toko", blank=True, default="SeellyPetshop@outlook.com")
    shipping_base_fee = models.PositiveIntegerField("Ongkir dasar (Rp)", default=5000)
    shipping_base_km = models.DecimalField("Jarak ongkir dasar (km)", max_digits=5, decimal_places=1, default=Decimal("3"))
    shipping_per_km = models.PositiveIntegerField("Ongkir per km berikutnya (Rp)", default=2000)
    max_delivery_km = models.DecimalField("Jarak antar maksimal (km)", max_digits=5, decimal_places=1, default=Decimal("25"))
    pickup_base_fee = models.PositiveIntegerField("Antar-jemput hewan dasar (Rp)", default=10000)
    pickup_base_km = models.DecimalField("Jarak antar-jemput dasar (km)", max_digits=5, decimal_places=1, default=Decimal("3"))
    pickup_per_km = models.PositiveIntegerField("Antar-jemput per km berikutnya (Rp)", default=3000)
    max_packages_per_courier = models.PositiveSmallIntegerField("Maks. paket per kurir per rute", default=10)
    payment_deadline_hours = models.PositiveSmallIntegerField(
        "Batas waktu bayar transfer/QRIS (jam)", default=1,
        help_text="Pesanan barang & booking layanan yang belum dibayar lewat batas ini dibatalkan otomatis.",
    )
    grooming_reminder_days = models.PositiveSmallIntegerField(
        "Ingatkan grooming lagi setelah (hari)", default=30
    )
    gps_stale_seconds = models.PositiveSmallIntegerField(
        "GPS kurir dianggap mati setelah (detik)", default=120
    )
    # Kasir (transaksi offline).
    tax_percent = models.DecimalField(
        "Pajak / PPN (%)", max_digits=5, decimal_places=2, default=Decimal("0"),
        help_text="Isi 0 bila toko belum memungut pajak.",
    )
    cashier_discount_limit = models.PositiveIntegerField(
        "Batas diskon kasir per transaksi (Rp)", default=50000,
        help_text="Diskon di atas batas ini hanya bisa diberikan Admin/Super Admin.",
    )
    return_days = models.PositiveSmallIntegerField("Batas retur (hari)", default=7)
    qris_image = models.ImageField(
        "Gambar QRIS toko", upload_to="store/qris", null=True, blank=True,
        help_text="QRIS statis dari bank (gratis). Ditampilkan di layar kasir; pembayaran tetap dicek manual.",
    )
    receipt_footer = models.CharField(
        "Catatan kaki struk", max_length=160, blank=True,
        default="Terima kasih telah berbelanja. Barang yang sudah dibeli dapat diretur maks. 7 hari dengan struk.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "pengaturan toko"
        verbose_name_plural = "pengaturan toko"

    def __str__(self):
        return self.name

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @property
    def location(self):
        return (float(self.latitude), float(self.longitude))

    @property
    def qris(self):
        """Gambar QRIS yang benar-benar ada di penyimpanan (None bila belum diunggah atau filenya hilang,
        mis. database disalin tanpa folder media), agar halaman tidak menampilkan gambar rusak."""
        image = self.qris_image
        if not image:
            return None
        try:
            return image if image.storage.exists(image.name) else None
        except Exception:
            return None

    @property
    def qris_missing(self):
        """QRIS tercatat di pengaturan tetapi filenya tidak ada: admin perlu mengunggah ulang."""
        return bool(self.qris_image) and self.qris is None

    @property
    def whatsapp_link(self):
        return f"https://wa.me/{self.whatsapp}"

    @property
    def whatsapp_display(self):
        digits = self.whatsapp
        if digits.startswith("62"):
            digits = "0" + digits[2:]
        return "-".join([digits[:4], digits[4:8], digits[8:]]).strip("-")

    @property
    def hours_display(self):
        return f"{self.open_hour:02d}.00–{self.close_hour:02d}.00 WITA"

    def distance_km(self, lat, lng):
        return haversine_km(self.latitude, self.longitude, lat, lng)

    def shipping_fee(self, distance_km):
        return tiered_fee(distance_km, self.shipping_base_fee, self.shipping_base_km, self.shipping_per_km)

    def pickup_fee(self, distance_km, trips=2):
        """Biaya antar-jemput hewan: tarif satu arah x jumlah perjalanan (jemput dan/atau antar pulang)."""
        one_way = tiered_fee(distance_km, self.pickup_base_fee, self.pickup_base_km, self.pickup_per_km)
        return one_way * trips

    def can_deliver_to(self, distance_km):
        return float(distance_km) <= float(self.max_delivery_km)

    def bank_accounts(self):
        return [
            {"bank": a.bank, "number": a.number, "holder": a.holder}
            for a in BankAccount.objects.filter(is_active=True)
        ]


class BankAccount(models.Model):
    bank = models.CharField("Bank", max_length=40)
    number = models.CharField("Nomor rekening", max_length=30)
    holder = models.CharField("Atas nama", max_length=80)
    is_active = models.BooleanField("Aktif", default=True)
    order = models.PositiveSmallIntegerField("Urutan", default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "rekening bank"
        verbose_name_plural = "rekening bank"

    def __str__(self):
        return f"{self.bank} {self.number} a.n. {self.holder}"


class NotificationQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(read_at__isnull=True)


# Notifikasi di dasbor (ikon lonceng). Gratis, tanpa WhatsApp API berbayar.
class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=255, blank=True, default="")
    url = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "notifikasi"
        verbose_name_plural = "notifikasi"

    def __str__(self):
        return self.title

    # Ikon dan warna kartu notifikasi, ditebak dari halaman tujuannya.
    ICONS = (
        (("/retur", "retur"), "bi-arrow-counterclockwise", "is-gold"),
        (("/grooming", "/service", "/booking", "/pet", "hewan"), "bi-heart", "is-pri"),
        (("/remittance", "/cash", "setoran"), "bi-wallet2", "is-gold"),
        (("/review", "ulasan"), "bi-star", "is-gold"),
        (("/complaint", "komplain"), "bi-chat-left-text", "is-bad"),
        (("/payment", "/pickup", "/packing", "/order", "/transaction", "/courier", "paket", "pesanan"), "bi-box-seam", "is-pri"),
    )

    @property
    def look(self):
        haystack = f"{self.url} {self.title}".lower()
        for keys, icon, tone in self.ICONS:
            if any(k in haystack for k in keys):
                return {"icon": icon, "tone": tone}
        return {"icon": "bi-bell", "tone": ""}

    @classmethod
    def send(cls, users, title, body="", url=""):
        """Kirim notifikasi ke satu user atau banyak user sekaligus."""
        if users is None:
            return
        if not isinstance(users, (list, tuple, set, models.QuerySet)):
            users = [users]
        cls.objects.bulk_create(
            [cls(user=u, title=title[:120], body=body[:255], url=url[:255]) for u in users if u]
        )

    @classmethod
    def to_staff(cls, roles, title, body="", url=""):
        from account.models import User

        cls.send(list(User.objects.filter(role__in=roles, is_active=True)), title, body, url)


# Riwayat status: siapa, kapan, apa, foto & koordinat (untuk menangani komplain).
class ActivityLog(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    subject = GenericForeignKey("content_type", "object_id")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=60)
    detail = models.CharField(max_length=255, blank=True, default="")
    photo = models.ImageField(upload_to="activity/%Y/%m", null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["content_type", "object_id"])]
        verbose_name = "riwayat status"
        verbose_name_plural = "riwayat status"

    def __str__(self):
        return f"{self.action} ({self.created_at:%d/%m %H:%M})"

    @classmethod
    def record(cls, subject, action, actor=None, detail="", photo=None, lat=None, lng=None):
        return cls.objects.create(
            content_type=ContentType.objects.get_for_model(subject),
            object_id=subject.pk,
            actor=actor if getattr(actor, "pk", None) else None,
            action=action[:60],
            detail=(detail or "")[:255],
            photo=photo,
            latitude=lat,
            longitude=lng,
        )

    @classmethod
    def for_object(cls, subject):
        return cls.objects.filter(
            content_type=ContentType.objects.get_for_model(subject), object_id=subject.pk
        ).select_related("actor")


class ComplaintCategory(models.TextChoices):
    PRODUCT = "PRODUK", _("Produk rusak / tidak sesuai")
    DELIVERY = "PENGIRIMAN", _("Pengiriman")
    SERVICE = "LAYANAN", _("Layanan grooming")
    PAYMENT = "PEMBAYARAN", _("Pembayaran")
    OTHER = "LAINNYA", _("Lainnya")


class ComplaintStatus(models.TextChoices):
    OPEN = "BARU", _("Baru")
    IN_PROGRESS = "DIPROSES", _("Diproses")
    RESOLVED = "SELESAI", _("Selesai")


# Komplain pelanggan (bisa dengan foto), ditangani admin/kasir dan dibalas lewat notifikasi.
class Complaint(models.Model):
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="complaints"
    )
    order = models.ForeignKey(
        "transaction.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints"
    )
    booking = models.ForeignKey(
        "service.ServiceBooking", on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints"
    )
    category = models.CharField(_("Kategori"), max_length=12, choices=ComplaintCategory.choices)
    message = models.TextField(_("Isi komplain"), max_length=1000)
    photo = models.ImageField(_("Foto"), upload_to="complaints/%Y/%m", null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=ComplaintStatus.choices, default=ComplaintStatus.OPEN, db_index=True
    )
    response = models.TextField(_("Balasan toko"), max_length=1000, blank=True, default="")
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "komplain"
        verbose_name_plural = "komplain"

    def __str__(self):
        return f"Komplain #{self.pk} ({self.get_category_display()})"

    @property
    def subject_label(self):
        if self.order_id:
            return f"Pesanan #{self.order_id}"
        if self.booking_id:
            return f"Booking #{self.booking_id}"
        return "Umum"

    def respond(self, staff, status, response):
        from common.exceptions import PetshopError

        if status not in ComplaintStatus.values:
            raise PetshopError("Status komplain tidak dikenal.")
        if status == ComplaintStatus.RESOLVED and not (response or "").strip():
            raise PetshopError("Tulis balasan sebelum menandai komplain selesai.")
        self.status = status
        self.response = (response or "").strip()[:1000]
        self.handled_by = staff
        self.responded_at = timezone.now()
        self.save(update_fields=["status", "response", "handled_by", "responded_at"])
