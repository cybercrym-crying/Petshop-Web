from django.utils.translation import gettext_lazy as _
import math
import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone

from common.exceptions import PetshopError
from common.models import TimeStampedModel
from product.models import PetType

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # tanpa 0/O/1/I agar mudah dibacakan


def new_checkin_code():
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


class BookingStatus(models.TextChoices):
    PENDING = "PENDING", _("Menunggu konfirmasi")
    SCHEDULED = "TERJADWAL", _("Terjadwal")
    PICKUP = "DIJEMPUT", _("Dijemput kurir")
    QUEUED = "ANTRE", _("Dalam antrean")
    PROCESS = "PROSES", _("Dikerjakan")
    READY = "SIAP", _("Siap diambil")
    RETURNING = "DIANTAR", _("Diantar pulang")
    DONE = "SELESAI", _("Selesai")
    CANCELLED = "BATAL", _("Dibatalkan")
    NO_SHOW = "TIDAK_DATANG", _("Tidak datang")


# Booking yang masih memakai slot groomer (dipakai cek kapasitas jadwal).
OPEN_BOOKING_STATUSES = (
    BookingStatus.PENDING,
    BookingStatus.SCHEDULED,
    BookingStatus.PICKUP,
    BookingStatus.QUEUED,
    BookingStatus.PROCESS,
)
# Status yang sudah lewat tahap pengerjaan groomer (untuk riwayat & statistik).
WORK_DONE_STATUSES = (BookingStatus.READY, BookingStatus.RETURNING, BookingStatus.DONE)

# Tahapan bawaan bila admin belum mengatur tahapan untuk sebuah layanan.
DEFAULT_STEPS = ["Pemeriksaan awal", "Pengerjaan layanan", "Pemeriksaan akhir"]


class InvalidBookingTransition(PetshopError):
    pass


class ServiceQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


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



    def step_names(self):
        names = list(self.steps.values_list("name", flat=True))
        return names or list(DEFAULT_STEPS)


# Tahapan kerja per layanan (diatur admin), mis. Grooming Lengkap:
# pemeriksaan awal -> potong kuku & telinga -> mandi -> pengeringan -> rapikan bulu -> finishing.
class ServiceStep(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="steps")
    position = models.PositiveSmallIntegerField("Urutan", default=1)
    name = models.CharField("Nama tahap", max_length=80)
    needs_photo = models.BooleanField("Wajib foto", default=True)

    class Meta:
        ordering = ["service", "position", "pk"]
        verbose_name = "tahapan layanan"
        verbose_name_plural = "tahapan layanan"

    def __str__(self):
        return f"{self.service}: {self.position}. {self.name}"


class PetSex(models.TextChoices):
    UNKNOWN = "", _("Tidak diketahui")
    MALE = "JANTAN", _("Jantan")
    FEMALE = "BETINA", _("Betina")


# Profil hewan milik pelanggan: dipakai ulang saat booking, riwayat perawatan & pengingat grooming.
class Pet(TimeStampedModel):
    owner = models.ForeignKey(
        "account.User", on_delete=models.CASCADE, related_name="pets",
        limit_choices_to={"role": "CUSTOMER"},
    )
    name = models.CharField(_("Nama hewan"), max_length=60)
    pet_type = models.CharField(
        _("Jenis hewan"), max_length=20,
        choices=[(c, label) for c, label in PetType.choices if c != PetType.ALL],
    )
    breed = models.CharField(_("Ras"), max_length=60, blank=True, default="")
    sex = models.CharField(_("Kelamin"), max_length=10, choices=PetSex.choices, blank=True, default="")
    birth_date = models.DateField(_("Tanggal lahir"), null=True, blank=True)
    weight_kg = models.DecimalField(_("Berat (kg)"), max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.CharField(
        _("Catatan kesehatan / kebiasaan"), max_length=255, blank=True, default="",
        help_text=_("Mis. alergi sampo tertentu, galak saat potong kuku."),
    )
    photo = models.ImageField(_("Foto"), upload_to="pets/%Y/%m", null=True, blank=True)
    reminded_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "hewan pelanggan"
        verbose_name_plural = "hewan pelanggan"

    def __str__(self):
        return f"{self.name} ({self.get_pet_type_display()})"

    @property
    def age_display(self):
        if not self.birth_date:
            return ""
        today = timezone.localdate()
        months = (today.year - self.birth_date.year) * 12 + today.month - self.birth_date.month
        if today.day < self.birth_date.day:
            months -= 1
        months = max(0, months)
        if months < 12:
            return f"{months} bulan"
        years, rest = divmod(months, 12)
        return f"{years} tahun" + (f" {rest} bulan" if rest else "")

    def last_service(self):
        return (
            self.bookings.filter(status__in=WORK_DONE_STATUSES)
            .select_related("service")
            .order_by("-finished_at")
            .first()
        )

    def grooming_due(self, days):
        """Sudah >= `days` hari sejak perawatan terakhir dan tidak ada booking yang berjalan."""
        if self.bookings.filter(status__in=OPEN_BOOKING_STATUSES).exists():
            return False
        last = self.last_service()
        if last is None or last.finished_at is None:
            return False
        return timezone.now() - last.finished_at >= timedelta(days=days)


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
    pet = models.ForeignKey(
        Pet, on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings"
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
    pet_name = models.CharField(_("Nama hewan"), max_length=60)
    pet_type = models.CharField(_("Jenis hewan"), max_length=20, choices=PetType.choices)
    schedule = models.DateTimeField("Jadwal")
    customer_note = models.CharField("Catatan pelanggan", max_length=255, blank=True, default="")
    # Harga disalin saat booking supaya perubahan harga layanan tidak mengubah riwayat.
    price = models.PositiveBigIntegerField("Harga")
    status = models.CharField(
        max_length=15,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
        db_index=True,
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        "account.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # QR di HP pelanggan: dipindai kasir saat check-in dan kurir saat jemput/antar hewan.
    checkin_code = models.CharField(max_length=8, default=new_checkin_code, editable=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        "account.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    checkin_weight_kg = models.DecimalField("Berat saat check-in (kg)", max_digits=5, decimal_places=2, null=True, blank=True)
    checkin_condition = models.CharField("Kondisi saat check-in", max_length=255, blank=True, default="")
    checkin_photo = models.ImageField(upload_to="bookings/checkin/%Y/%m", null=True, blank=True)
    queue_date = models.DateField(null=True, blank=True, db_index=True)
    queue_seq = models.PositiveIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)  # pengerjaan groomer selesai
    groomer_note = models.CharField("Catatan groomer", max_length=255, blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)  # hewan sudah kembali ke pemilik
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # Antar-jemput hewan oleh kurir yang bisa membawa hewan.
    pickup_requested = models.BooleanField("Minta dijemput", default=False)
    return_requested = models.BooleanField("Minta diantar pulang", default=False)
    transport_address = models.CharField("Alamat jemput/antar", max_length=255, blank=True, default="")
    transport_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    transport_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    transport_distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    transport_fee = models.PositiveIntegerField("Biaya antar-jemput", default=0)
    pet_courier = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, null=True, blank=True, related_name="pet_trips",
        limit_choices_to={"role": "KURIR"},
    )
    transport_started_at = models.DateTimeField(null=True, blank=True)
    pet_collected_at = models.DateTimeField(null=True, blank=True)
    pickup_photo = models.ImageField(upload_to="bookings/transport/%Y/%m", null=True, blank=True)
    return_photo = models.ImageField(upload_to="bookings/transport/%Y/%m", null=True, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    review = models.CharField("Ulasan", max_length=255, blank=True, default="")
    rated_at = models.DateTimeField(null=True, blank=True)

    # OOP: ENKAPSULASI - alur status booking dijaga di satu tempat.
    _ALLOWED_TRANSITIONS = {
        BookingStatus.PENDING: {BookingStatus.SCHEDULED, BookingStatus.QUEUED, BookingStatus.CANCELLED, BookingStatus.NO_SHOW},
        BookingStatus.SCHEDULED: {BookingStatus.PICKUP, BookingStatus.QUEUED, BookingStatus.CANCELLED, BookingStatus.NO_SHOW},
        BookingStatus.PICKUP: {BookingStatus.QUEUED, BookingStatus.CANCELLED},
        BookingStatus.QUEUED: {BookingStatus.PROCESS, BookingStatus.CANCELLED},
        BookingStatus.PROCESS: {BookingStatus.READY},
        BookingStatus.READY: {BookingStatus.RETURNING, BookingStatus.DONE},
        BookingStatus.RETURNING: {BookingStatus.DONE},
    }

    class Meta:
        ordering = ["schedule", "pk"]
        verbose_name = "booking layanan"
        verbose_name_plural = "booking layanan"
        constraints = [
            models.UniqueConstraint(
                fields=["queue_date", "queue_seq"], name="unique_booking_queue_number"
            )
        ]

    def __str__(self):
        return f"Booking #{self.pk} - {self.service} ({self.pet_name})"

    def save(self, *args, **kwargs):
        if self.price is None and self.service_id:
            self.price = self.service.price
        super().save(*args, **kwargs)

    @classmethod
    def book(
        cls,
        *,
        customer,
        service,
        pet_name,
        pet_type,
        schedule,
        note="",
        created_by=None,
        groomer=None,
        check_capacity=False,
        pet=None,
        pickup=False,
        return_trip=False,
        location=None,
        address="",
        confirmed=False,
    ):
        """Satu pintu membuat booking baru (dari situs pelanggan atau kasir).

        check_capacity=True (booking online pelanggan) menolak jadwal yang sudah
        penuh. Kasir/admin boleh tetap menambah booking walk-in karena mereka
        melihat kondisi toko secara langsung; booking dari staf langsung Terjadwal.
        """
        from store.models import StoreSettings

        if not service.is_active:
            raise InvalidBookingTransition(f"Layanan '{service.name}' sedang tidak tersedia.")
        if pet is not None:
            if pet.owner_id != customer.pk:
                raise InvalidBookingTransition("Hewan ini bukan milik pelanggan tersebut.")
            pet_name, pet_type = pet.name, pet.pet_type
        if not service.suits(pet_type):
            raise InvalidBookingTransition(
                f"Layanan '{service.name}' khusus {service.get_pet_type_display().lower()}."
            )
        if check_capacity and not cls.slot_available(schedule, service.duration_minutes):
            raise InvalidBookingTransition(
                "Jadwal tersebut sudah penuh. Silakan pilih jam lain."
            )
        transport = {}
        if pickup or return_trip:
            if not location:
                raise InvalidBookingTransition("Tandai lokasi jemput/antar di peta.")
            store = StoreSettings.current()
            lat, lng = location
            km = store.distance_km(lat, lng)
            if not store.can_deliver_to(km):
                raise InvalidBookingTransition(
                    f"Lokasi ±{km:.1f} km dari toko, di luar jangkauan antar-jemput ({store.max_delivery_km} km)."
                )
            transport = dict(
                pickup_requested=bool(pickup),
                return_requested=bool(return_trip),
                transport_address=(address or customer.address or "").strip()[:255],
                transport_latitude=lat,
                transport_longitude=lng,
                transport_distance_km=round(km, 2),
                transport_fee=store.pickup_fee(km, trips=int(bool(pickup)) + int(bool(return_trip))),
            )
        now = timezone.now()
        return cls.objects.create(
            customer=customer,
            service=service,
            pet=pet,
            pet_name=pet_name.strip(),
            pet_type=pet_type,
            schedule=schedule,
            customer_note=(note or "").strip()[:255],
            created_by=created_by,
            groomer=groomer,
            price=service.price,
            status=BookingStatus.SCHEDULED if confirmed else BookingStatus.PENDING,
            confirmed_at=now if confirmed else None,
            confirmed_by=created_by if confirmed else None,
            **transport,
        )

    @classmethod
    def capacity(cls):
        """Jumlah booking yang bisa dikerjakan bersamaan = jumlah groomer aktif (min. 1)."""
        from account.models import User

        return max(1, User.groomers().count())

    @classmethod
    def slot_available(cls, schedule, duration_minutes, exclude_pk=None):
        """True bila jadwal [schedule, schedule+durasi) masih punya groomer kosong."""
        end = schedule + timedelta(minutes=duration_minutes)
        day_start = schedule - timedelta(hours=24)
        overlapping = 0
        candidates = cls.objects.filter(
            status__in=OPEN_BOOKING_STATUSES,
            schedule__lt=end,
            schedule__gt=day_start,
        ).select_related("service")
        if exclude_pk:
            candidates = candidates.exclude(pk=exclude_pk)
        for other in candidates:
            other_end = other.schedule + timedelta(minutes=other.service.duration_minutes)
            if other_end > schedule:
                overlapping += 1
        return overlapping < cls.capacity()

    # ------------------------------------------------------------------
    # Info tampilan
    # ------------------------------------------------------------------

    @property
    def is_open(self):
        return self.status in self._ALLOWED_TRANSITIONS

    @property
    def can_cancel(self):
        return self.status in (BookingStatus.PENDING, BookingStatus.SCHEDULED)

    @property
    def can_check_in(self):
        if self.status == BookingStatus.PICKUP:
            return self.pet_collected_at is not None
        return self.status in (BookingStatus.PENDING, BookingStatus.SCHEDULED)

    @property
    def is_today(self):
        return timezone.localdate(self.schedule) == timezone.localdate()

    @property
    def is_late(self):
        """Belum datang padahal jadwalnya sudah lewat."""
        return (
            self.status in (BookingStatus.PENDING, BookingStatus.SCHEDULED)
            and self.schedule < timezone.now()
        )

    @property
    def needs_transport(self):
        return self.pickup_requested or self.return_requested

    @property
    def total_price(self):
        return self.price + self.transport_fee

    @property
    def payment_line(self):
        """Baris pembayaran di kasir (None bila belum dibayar / transaksinya dibatalkan)."""
        return (
            self.payment_lines.exclude(order__order_status="DIBATALKAN")
            .select_related("order").first()
        )

    @property
    def is_paid(self):
        return self.payment_line is not None

    @property
    def queue_label(self):
        return f"G-{self.queue_seq:03d}" if self.queue_seq else ""

    @property
    def checkin_payload(self):
        return f"PSB:{self.pk}:{self.checkin_code}"

    @property
    def in_transport(self):
        return self.status in (BookingStatus.PICKUP, BookingStatus.RETURNING)

    def check_code(self, scanned):
        """Terima isi QR (PSB:<id>:<kode>) atau kode 8 huruf yang dibacakan pelanggan."""
        text = (scanned or "").strip().upper()
        if text.startswith("PSB:"):
            parts = text.split(":")
            if len(parts) != 3 or parts[1] != str(self.pk):
                return False
            text = parts[2]
        return secrets.compare_digest(text, self.checkin_code)

    @classmethod
    def find_by_code(cls, scanned):
        text = (scanned or "").strip().upper()
        if text.startswith("PSB:"):
            parts = text.split(":")
            if len(parts) == 3 and parts[1].isdigit():
                booking = cls.objects.filter(pk=int(parts[1])).first()
                return booking if booking and booking.check_code(text) else None
            return None
        digits = text.lstrip("#")
        if digits.isdigit():
            return None  # nomor booking saja tidak cukup: harus QR atau kode rahasia
        return cls.objects.filter(checkin_code=text).exclude(status__in=[BookingStatus.DONE, BookingStatus.CANCELLED]).first()

    def queue_position(self):
        """Jumlah hewan yang antre di depan (0 = berikutnya dikerjakan)."""
        if self.status != BookingStatus.QUEUED or not self.queue_seq:
            return None
        return ServiceBooking.objects.filter(
            status=BookingStatus.QUEUED, queue_date=self.queue_date, queue_seq__lt=self.queue_seq
        ).count()

    def queue_eta_minutes(self):
        """Perkiraan mulai dikerjakan: sisa pekerjaan yang berjalan + antrean di depan, dibagi jumlah groomer."""
        if self.status != BookingStatus.QUEUED:
            return None
        now = timezone.now()
        ahead = ServiceBooking.objects.filter(
            status=BookingStatus.QUEUED, queue_date=self.queue_date, queue_seq__lt=self.queue_seq
        ).select_related("service")
        minutes = sum(b.service.duration_minutes for b in ahead)
        for b in ServiceBooking.objects.filter(status=BookingStatus.PROCESS).select_related("service"):
            elapsed = (now - b.started_at).total_seconds() / 60 if b.started_at else 0
            minutes += max(0, b.service.duration_minutes - elapsed)
        return int(math.ceil(minutes / self.capacity()))

    def progress(self):
        """(selesai, total) tahapan pengerjaan."""
        steps = list(self.steps.all())
        return sum(1 for s in steps if s.done_at), len(steps)

    def next_step(self):
        return self.steps.filter(done_at__isnull=True).order_by("position", "pk").first()

    # ------------------------------------------------------------------
    # Perpindahan status
    # ------------------------------------------------------------------

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

    def _check_pet_courier(self, courier):
        if self.pet_courier_id != getattr(courier, "pk", None):
            raise InvalidBookingTransition(f"Booking #{self.pk} bukan tugas antar-jemput Anda.")

    # Satu kurir satu jenis tugas: selama antar-jemput hewan berjalan, kurir tidak membawa paket,
    # dan sebaliknya (hewan tidak ikut berdesakan dengan paket di motor).
    @classmethod
    def active_trip(cls, courier):
        """Antar-jemput hewan yang sedang dijalankan kurir ini (sudah berangkat, belum selesai)."""
        return (
            cls.objects.filter(pet_courier=courier, status__in=[BookingStatus.PICKUP, BookingStatus.RETURNING])
            .order_by("transport_started_at")
            .first()
        )

    @staticmethod
    def _check_no_packages(courier):
        from transaction.models import Order, OrderStatus

        carrying = Order.objects.filter(courier=courier, order_status=OrderStatus.ON_DELIVERY).count()
        if carrying:
            raise InvalidBookingTransition(
                f"Anda masih membawa {carrying} paket. Antar semua paket dulu sebelum antar-jemput hewan."
            )

    def confirm(self, staff):
        """Kasir/admin menyetujui booking online: Menunggu konfirmasi -> Terjadwal."""
        if self.status != BookingStatus.PENDING:
            raise InvalidBookingTransition(f"Booking #{self.pk} sudah dikonfirmasi.")
        self._move_to(BookingStatus.SCHEDULED)
        self.confirmed_at = timezone.now()
        self.confirmed_by = staff
        self.save(update_fields=["status", "confirmed_at", "confirmed_by", "updated_at"])

    def cancel(self):
        """Batalkan booking yang belum dikerjakan (oleh pelanggan atau admin/kasir)."""
        if self.status == BookingStatus.PICKUP and self.pet_collected_at:
            raise InvalidBookingTransition(
                f"Booking #{self.pk}: hewan sudah dibawa kurir, check-in dulu lalu hubungi pemilik."
            )
        self._move_to(BookingStatus.CANCELLED)
        self.cancelled_at = timezone.now()
        self.save(update_fields=["status", "cancelled_at", "updated_at"])

    def cancel_by_customer(self, customer):
        if self.customer_id != customer.pk:
            raise InvalidBookingTransition("Booking ini bukan milik Anda.")
        if not self.can_cancel:
            raise InvalidBookingTransition(
                f"Booking #{self.pk} sudah berjalan, hubungi admin untuk pembatalan."
            )
        self.cancel()

    def mark_no_show(self):
        if self.schedule > timezone.now():
            raise InvalidBookingTransition(f"Jadwal booking #{self.pk} belum lewat.")
        self._move_to(BookingStatus.NO_SHOW)
        self.save(update_fields=["status", "updated_at"])

    def assign_groomer(self, groomer):
        """Admin/kasir menugaskan groomer selama booking belum dikerjakan."""
        self._check_groomer(groomer)
        if self.status not in OPEN_BOOKING_STATUSES or self.status == BookingStatus.PROCESS:
            raise InvalidBookingTransition(
                f"Booking #{self.pk}: groomer hanya bisa diganti sebelum dikerjakan."
            )
        self.groomer = groomer
        self.save(update_fields=["groomer", "updated_at"])

    def assign_pet_courier(self, courier):
        from account.models import User

        if not self.needs_transport:
            raise InvalidBookingTransition(f"Booking #{self.pk} tidak meminta antar-jemput.")
        if courier is None or not User.pet_couriers().filter(pk=courier.pk).exists():
            raise InvalidBookingTransition("Pilih kurir yang ditandai 'Bisa antar-jemput hewan'.")
        if self.status in (BookingStatus.PICKUP, BookingStatus.RETURNING) or not self.is_open:
            raise InvalidBookingTransition(f"Booking #{self.pk}: kurir tidak bisa diganti saat ini.")
        self.pet_courier = courier
        self.save(update_fields=["pet_courier", "updated_at"])

    def start_pickup(self, courier):
        """Kurir berangkat menjemput hewan: Terjadwal -> Dijemput kurir."""
        self._check_pet_courier(courier)
        if not self.pickup_requested:
            raise InvalidBookingTransition(f"Booking #{self.pk} tidak meminta penjemputan.")
        if self.status == BookingStatus.PENDING:
            raise InvalidBookingTransition(f"Booking #{self.pk} belum dikonfirmasi toko.")
        self._check_no_packages(courier)
        self._move_to(BookingStatus.PICKUP)
        self.transport_started_at = timezone.now()
        self.save(update_fields=["status", "transport_started_at", "updated_at"])

    def collect_pet(self, courier, code, photo):
        """Di rumah pelanggan: QR/kode cocok + foto hewan saat diterima kurir."""
        self._check_pet_courier(courier)
        if self.status != BookingStatus.PICKUP or self.pet_collected_at:
            raise InvalidBookingTransition(f"Booking #{self.pk} tidak sedang dijemput.")
        if not self.check_code(code):
            raise InvalidBookingTransition("QR / kode booking tidak cocok.")
        if photo is None:
            raise InvalidBookingTransition("Foto hewan saat dijemput wajib diambil.")
        self.pickup_photo = photo
        self.pet_collected_at = timezone.now()
        self.save(update_fields=["pickup_photo", "pet_collected_at", "updated_at"])

    def check_in(self, staff, weight_kg=None, condition="", photo=None):
        """Hewan tiba di toko: cek kesehatan singkat lalu dapat nomor antrean harian (G-001, ...)."""
        if not self.can_check_in:
            raise InvalidBookingTransition(
                f"Booking #{self.pk} berstatus {self.get_status_display()}, tidak bisa check-in."
            )
        self._move_to(BookingStatus.QUEUED)
        today = timezone.localdate()
        last = (
            ServiceBooking.objects.select_for_update()
            .filter(queue_date=today)
            .aggregate(m=models.Max("queue_seq"))["m"]
            or 0
        )
        self.queue_date = today
        self.queue_seq = last + 1
        self.checked_in_at = timezone.now()
        self.checked_in_by = staff
        self.checkin_weight_kg = weight_kg
        self.checkin_condition = (condition or "").strip()[:255]
        fields = [
            "status", "queue_date", "queue_seq", "checked_in_at", "checked_in_by",
            "checkin_weight_kg", "checkin_condition", "updated_at",
        ]
        if photo is not None:
            self.checkin_photo = photo
            fields.append("checkin_photo")
        self.save(update_fields=fields)
        if self.pet_id and weight_kg:
            Pet.objects.filter(pk=self.pet_id).update(weight_kg=weight_kg)

    def start(self, groomer):
        """Groomer mengambil hewan dari antrean: Dalam antrean -> Dikerjakan."""
        self._check_groomer(groomer)
        if self.groomer_id and self.groomer_id != groomer.pk:
            raise InvalidBookingTransition(
                f"Booking #{self.pk} sudah ditugaskan ke groomer lain."
            )
        self._move_to(BookingStatus.PROCESS)
        self.groomer = groomer
        self.started_at = timezone.now()
        self.save(update_fields=["status", "groomer", "started_at", "updated_at"])
        self._create_steps()

    def _create_steps(self):
        templates = list(self.service.steps.all())
        if templates:
            rows = [BookingStep(booking=self, position=n, name=t.name, needs_photo=t.needs_photo)
                    for n, t in enumerate(templates, start=1)]
        else:
            rows = [BookingStep(booking=self, position=n, name=name)
                    for n, name in enumerate(DEFAULT_STEPS, start=1)]
        BookingStep.objects.bulk_create(rows)

    def complete_step(self, groomer, photo=None, note=""):
        """Selesaikan tahap berikutnya (berurutan). Tahap terakhir -> Siap diambil otomatis."""
        if self.groomer_id != getattr(groomer, "pk", None):
            raise InvalidBookingTransition(f"Booking #{self.pk} bukan tugas Anda.")
        if self.status != BookingStatus.PROCESS:
            raise InvalidBookingTransition(f"Booking #{self.pk} tidak sedang dikerjakan.")
        if not self.steps.exists():
            self._create_steps()  # booking lama yang dimulai sebelum ada tahapan
        step = self.next_step()
        if step is None:
            raise InvalidBookingTransition("Semua tahap sudah selesai.")
        if step.needs_photo and photo is None:
            raise InvalidBookingTransition(f"Tahap '{step.name}' wajib difoto.")
        step.done_at = timezone.now()
        step.done_by = groomer
        step.note = (note or "").strip()[:255]
        if photo is not None:
            step.photo = photo
        step.save()
        if self.next_step() is None:
            self._move_to(BookingStatus.READY)
            self.finished_at = timezone.now()
            if step.note:
                self.groomer_note = step.note
            self.save(update_fields=["status", "finished_at", "groomer_note", "updated_at"])
        return step

    def hand_to_owner(self):
        """Pemilik mengambil hewan di toko: Siap diambil -> Selesai."""
        if self.status != BookingStatus.READY:
            raise InvalidBookingTransition(f"Booking #{self.pk} belum siap diambil.")
        self._move_to(BookingStatus.DONE)
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at", "updated_at"])

    def start_return(self, courier, photo):
        """Kurir membawa hewan pulang: Siap diambil -> Diantar pulang (foto saat berangkat)."""
        self._check_pet_courier(courier)
        if not self.return_requested:
            raise InvalidBookingTransition(f"Booking #{self.pk} tidak meminta diantar pulang.")
        if photo is None:
            raise InvalidBookingTransition("Foto hewan saat dibawa pulang wajib diambil.")
        self._check_no_packages(courier)
        self._move_to(BookingStatus.RETURNING)
        self.transport_started_at = timezone.now()
        self.save(update_fields=["status", "transport_started_at", "updated_at"])
        return photo

    def deliver_pet(self, courier, code, photo):
        """Hewan diserahkan ke pemilik: QR/kode cocok + foto -> Selesai."""
        self._check_pet_courier(courier)
        if self.status != BookingStatus.RETURNING:
            raise InvalidBookingTransition(f"Booking #{self.pk} tidak sedang diantar pulang.")
        if not self.check_code(code):
            raise InvalidBookingTransition("QR / kode booking tidak cocok.")
        if photo is None:
            raise InvalidBookingTransition("Foto hewan saat diserahkan wajib diambil.")
        self._move_to(BookingStatus.DONE)
        self.return_photo = photo
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "return_photo", "closed_at", "updated_at"])

    def rate(self, customer, stars, review=""):
        if self.customer_id != customer.pk:
            raise InvalidBookingTransition("Booking ini bukan milik Anda.")
        if self.status != BookingStatus.DONE:
            raise InvalidBookingTransition("Ulasan bisa diberikan setelah layanan selesai.")
        if self.rating:
            raise InvalidBookingTransition("Booking ini sudah diberi ulasan.")
        if stars not in range(1, 6):
            raise InvalidBookingTransition("Pilih 1 sampai 5 bintang.")
        self.rating = stars
        self.review = (review or "").strip()[:255]
        self.rated_at = timezone.now()
        self.save(update_fields=["rating", "review", "rated_at", "updated_at"])


class BookingStep(models.Model):
    booking = models.ForeignKey(ServiceBooking, on_delete=models.CASCADE, related_name="steps")
    position = models.PositiveSmallIntegerField(default=1)
    name = models.CharField(max_length=80)
    needs_photo = models.BooleanField(default=True)
    photo = models.ImageField(upload_to="bookings/steps/%Y/%m", null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    done_at = models.DateTimeField(null=True, blank=True)
    done_by = models.ForeignKey(
        "account.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["booking", "position", "pk"]
        verbose_name = "tahap pengerjaan"
        verbose_name_plural = "tahap pengerjaan"

    def __str__(self):
        return f"#{self.booking_id} {self.position}. {self.name}"
