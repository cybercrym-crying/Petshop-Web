from django.db import models
from django.utils import timezone

from common.exceptions import PetshopError
from common.models import TimeStampedModel
from product.models import PetType


class BookingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESS = "PROSES", "Proses"
    DONE = "SELESAI", "Selesai"


class InvalidBookingTransition(PetshopError):
    pass


class ServiceQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


# Jenis jasa yang dijual toko (grooming, mandi, potong kuku, dst).
class Service(TimeStampedModel):
    name = models.CharField("Nama layanan", max_length=120, unique=True)
    description = models.TextField("Deskripsi", blank=True, default="")
    price = models.PositiveBigIntegerField("Harga")
    duration_minutes = models.PositiveIntegerField("Durasi (menit)", default=60)
    pet_type = models.CharField(
        "Untuk hewan", max_length=20, choices=PetType.choices, default=PetType.ALL
    )
    is_active = models.BooleanField("Aktif", default=True)

    objects = ServiceQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        verbose_name = "layanan"
        verbose_name_plural = "layanan"

    def __str__(self):
        return self.name

    def suits(self, pet_type):
        return self.pet_type in (PetType.ALL, pet_type)


class ServiceBooking(TimeStampedModel):
    customer = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="service_bookings",
        limit_choices_to={"role": "CUSTOMER"},
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name="bookings"
    )
    groomer = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="grooming_jobs",
        limit_choices_to={"role": "GROOMER"},
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "account.User",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
    )
    pet_name = models.CharField("Nama hewan", max_length=60)
    pet_type = models.CharField("Jenis hewan", max_length=20, choices=PetType.choices)
    schedule = models.DateTimeField("Jadwal")
    customer_note = models.CharField("Catatan pelanggan", max_length=255, blank=True, default="")
    # Harga disalin saat booking supaya perubahan harga layanan tidak mengubah riwayat.
    price = models.PositiveBigIntegerField("Harga")
    status = models.CharField(
        max_length=10,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    groomer_note = models.CharField("Catatan groomer", max_length=255, blank=True, default="")

    # OOP: ENKAPSULASI - urutan status hanya Pending -> Proses -> Selesai.
    _ALLOWED_TRANSITIONS = {
        BookingStatus.PENDING: {BookingStatus.PROCESS},
        BookingStatus.PROCESS: {BookingStatus.DONE},
    }

    class Meta:
        ordering = ["schedule", "pk"]
        verbose_name = "booking layanan"
        verbose_name_plural = "booking layanan"

    def __str__(self):
        return f"Booking #{self.pk} - {self.service} ({self.pet_name})"

    def save(self, *args, **kwargs):
        if self.price is None and self.service_id:
            self.price = self.service.price
        super().save(*args, **kwargs)

    @classmethod
    def book(cls, *, customer, service, pet_name, pet_type, schedule, note="", created_by=None, groomer=None):
        """Satu pintu membuat booking baru (dari situs pelanggan atau kasir)."""
        if not service.is_active:
            raise InvalidBookingTransition(f"Layanan '{service.name}' sedang tidak tersedia.")
        if not service.suits(pet_type):
            raise InvalidBookingTransition(
                f"Layanan '{service.name}' khusus {service.get_pet_type_display().lower()}."
            )
        return cls.objects.create(
            customer=customer,
            service=service,
            pet_name=pet_name.strip(),
            pet_type=pet_type,
            schedule=schedule,
            customer_note=(note or "").strip()[:255],
            created_by=created_by,
            groomer=groomer,
            price=service.price,
        )

    @property
    def is_open(self):
        return self.status in self._ALLOWED_TRANSITIONS

    @property
    def is_today(self):
        return timezone.localdate(self.schedule) == timezone.localdate()

    @property
    def is_late(self):
        """Masih pending padahal jadwalnya sudah lewat."""
        return self.status == BookingStatus.PENDING and self.schedule < timezone.now()

    def _move_to(self, new_status):
        if new_status not in self._ALLOWED_TRANSITIONS.get(self.status, set()):
            raise InvalidBookingTransition(
                f"Booking #{self.pk}: status {BookingStatus(self.status).label} "
                f"tidak bisa diubah ke {BookingStatus(new_status).label}."
            )
        self.status = new_status

    @staticmethod
    def _check_groomer(user):
        if user is None or user.role != "GROOMER":
            raise InvalidBookingTransition("Pilih groomer terlebih dahulu.")

    def assign_groomer(self, groomer):
        """Admin/kasir menugaskan groomer; hanya selama booking masih Pending."""
        self._check_groomer(groomer)
        if self.status != BookingStatus.PENDING:
            raise InvalidBookingTransition(
                f"Booking #{self.pk}: groomer hanya bisa diganti saat status Pending."
            )
        self.groomer = groomer
        self.save(update_fields=["groomer", "updated_at"])

    def start(self, groomer):
        """Groomer mengambil booking: Pending -> Proses."""
        self._check_groomer(groomer)
        if self.groomer_id and self.groomer_id != groomer.pk:
            raise InvalidBookingTransition(
                f"Booking #{self.pk} sudah ditugaskan ke groomer lain."
            )
        self._move_to(BookingStatus.PROCESS)
        self.groomer = groomer
        self.started_at = timezone.now()
        self.save(update_fields=["status", "groomer", "started_at", "updated_at"])

    def finish(self, groomer, note=""):
        """Groomer menyelesaikan booking miliknya: Proses -> Selesai."""
        if self.groomer_id != getattr(groomer, "pk", None):
            raise InvalidBookingTransition(
                f"Booking #{self.pk} bukan tugas Anda."
            )
        self._move_to(BookingStatus.DONE)
        self.finished_at = timezone.now()
        self.groomer_note = (note or "").strip()[:255]
        self.save(update_fields=["status", "finished_at", "groomer_note", "updated_at"])
