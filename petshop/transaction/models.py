from django.utils.translation import gettext_lazy as _
import secrets
import uuid
from urllib.parse import quote
from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from product.models import Product, MutationType, InsufficientStock
from common.exceptions import PetshopError
from common.models import TimeStampedModel
from abc import ABC, abstractmethod

UNPAID_GRACE = timedelta(hours=1)  # batas toleransi transfer belum dibayar

# Resi: tanpa 0/O/1/I/L supaya tidak salah baca saat diketik pelanggan.
TRACKING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TRACKING_SUFFIX_LENGTH = 6


def normalize_tracking_number(raw):
    """'ps 241022 k7m2qx' / 'PS241022K7M2QX' -> 'PS-241022-K7M2QX'."""
    compact = "".join(ch for ch in (raw or "").upper() if ch.isalnum())
    if len(compact) != 2 + 6 + TRACKING_SUFFIX_LENGTH or not compact.startswith("PS"):
        return ""
    return f"PS-{compact[2:8]}-{compact[8:]}"


def new_tracking_number(when=None):
    """Resi acak berformat PS-YYMMDD-XXXXXX (suffix acak, tidak bisa ditebak urut)."""
    when = when or timezone.localtime()
    suffix = "".join(
        secrets.choice(TRACKING_ALPHABET) for _ in range(TRACKING_SUFFIX_LENGTH)
    )
    return f"PS-{when:%y%m%d}-{suffix}"


def payment_proof_path(instance, filename):
    """Foto bukti transfer; nama diacak supaya tidak bisa ditebak."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"payment_proofs/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.{extension}"


HANDOVER_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_handover_code():
    """Kode serah-terima rahasia: hanya tampil di akun pelanggan, discan kurir saat paket diserahkan."""
    return "".join(secrets.choice(HANDOVER_ALPHABET) for _ in range(8))


def delivery_proof_path(instance, filename):
    """Nama file diacak (uuid) supaya URL foto bukti tidak bisa ditebak."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"delivery_proofs/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.{extension}"


# OOP: ABSTRAKSI - Payment hanya mendefinisikan "apa" yang harus bisa dilakukan
# metode pembayaran, tanpa isi. Cara kerjanya diserahkan ke subclass.
class Payment(ABC):
    code = None

    @abstractmethod
    def paid_after_accepted(self) -> bool: ...

    @abstractmethod
    def can_be_late(self) -> bool: ...

    @abstractmethod
    def must_be_paid_before_delivery(self) -> bool: ...


# OOP: PEWARISAN - Cash mewarisi Payment.
# OOP: POLIMORFISME - method yang sama (can_be_late, dst) menjawab beda
# tergantung kelasnya; pemanggil cukup `order.payment_handler.can_be_late()`.
class Cash(Payment):
    code = "TUNAI"

    def paid_after_accepted(self):
        return True

    def can_be_late(self):
        return False

    def must_be_paid_before_delivery(self):
        return False


# OOP: PEWARISAN + POLIMORFISME - Transfer menjawab method yang sama dengan
# hasil berbeda dari Cash.
class Transfer(Payment):
    code = "TRANSFER"

    def paid_after_accepted(self):
        return False

    def can_be_late(self):
        return True

    def must_be_paid_before_delivery(self):
        return True


# QRIS statis toko: dicek manual seperti transfer (tanpa payment gateway).
class Qris(Transfer):
    code = "QRIS"


# Bayar campuran hanya terjadi di kasir dan selalu lunas di tempat.
class Mixed(Transfer):
    code = "CAMPURAN"


PAYMENT_REGISTRY = {
    payment_class.code: payment_class() for payment_class in (Cash, Transfer, Qris, Mixed)
}


def get_payment(code):
    return PAYMENT_REGISTRY[code]


class CheckoutError(PetshopError):
    pass


class InvalidTransition(PetshopError):
    pass


class PriceChanged(CheckoutError):
    """Total di keranjang pelanggan berbeda dengan harga terbaru di database."""

    def __init__(self, total):
        self.total = total
        super().__init__(
            "Harga atau ketersediaan barang berubah sejak keranjang dibuka. "
            "Periksa kembali total terbaru lalu pesan ulang."
        )


class PaymentMethod(models.TextChoices):
    CASH = "TUNAI", _("Tunai")
    TRANSFER = "TRANSFER", _("Transfer")
    QRIS = "QRIS", _("QRIS")
    MIXED = "CAMPURAN", _("Campuran")


# Pesanan online hanya tunai (COD) atau transfer; QRIS & bayar campuran hanya di kasir.
ONLINE_PAYMENT_METHODS = (PaymentMethod.CASH, PaymentMethod.TRANSFER)
# Metode untuk satu baris pembayaran di kasir (CAMPURAN = gabungan baris-baris ini).
COUNTER_PAYMENT_METHODS = (PaymentMethod.CASH, PaymentMethod.TRANSFER, PaymentMethod.QRIS)


class Fulfillment(models.TextChoices):
    DELIVERY = "DIANTAR", _("Diantar")
    TAKE_AWAY = "BAWA", _("Dibawa langsung")


class PaymentStatus(models.TextChoices):
    PENDING = "MENUNGGU", _("Menunggu")
    PAID = "LUNAS", _("Lunas")


class OrderStatus(models.TextChoices):
    PENDING = "MENUNGGU", _("Menunggu Konfirmasi")
    CONFIRMED = "DIKONFIRMASI", _("Dikonfirmasi")
    ON_DELIVERY = "DALAM_PENGIRIMAN", _("Dalam Pengiriman")
    DELIVERED = "TERKIRIM", _("Terkirim")
    CANCELLED = "DIBATALKAN", _("Dibatalkan")


class OrderChannel(models.TextChoices):
    STORE = "TOKO", _("Toko / Kasir")
    ONLINE = "ONLINE", _("Online (situs)")


ONLINE_MAX_QTY = 99  # batas wajar per barang untuk satu pesanan online


class Order(models.Model):
    # Pegawai yang membuat (kasir/admin) atau yang mengonfirmasi order online.
    # Kosong selama order online belum dikonfirmasi.
    admin = models.ForeignKey(
        "account.User", on_delete=models.PROTECT, null=True, blank=True
    )
    courier = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="orders_as_courier",
        null=True,
        blank=True,
    )
    # Pelanggan = User ber-role CUSTOMER (tabel Customer lama sudah dihapus).
    customer = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="orders",
        limit_choices_to={"role": "CUSTOMER"},
    )
    order_status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.CONFIRMED,
    )
    payment_method = models.CharField(max_length=50, choices=PaymentMethod.choices)
    payment_status = models.CharField(
        max_length=50, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    total_payment = models.PositiveBigIntegerField(default=0)
    date = models.DateTimeField(default=timezone.now)

    # Resi transaksi: dibuat otomatis saat order dibuat, dibagikan ke pelanggan.
    tracking_number = models.CharField(
        max_length=20, unique=True, null=True, blank=True, editable=False
    )
    # Jejak pengiriman: kapan mulai diantar, kapan sampai, dan bukti foto kurir.
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_photo = models.ImageField(
        upload_to=delivery_proof_path, null=True, blank=True
    )
    delivery_note = models.CharField(max_length=255, blank=True, default="")

    channel = models.CharField(
        max_length=10, choices=OrderChannel.choices, default=OrderChannel.STORE
    )
    customer_note = models.CharField(max_length=255, blank=True, default="")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Alamat disalin saat order dibuat supaya riwayat tidak ikut berubah ketika
    # pelanggan mengganti alamat akunnya.
    shipping_address = models.CharField(max_length=255, blank=True, default="")
    # Token sekali pakai dari browser: klik/kirim ulang tidak membuat order ganda.
    client_token = models.CharField(
        max_length=64, unique=True, null=True, blank=True, editable=False
    )

    # Titik antar dari pin peta pelanggan + ongkir yang dihitung server.
    delivery_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_distance_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    shipping_fee = models.PositiveBigIntegerField("Ongkir", default=0)

    # Transfer manual: batas bayar, foto bukti, dan siapa yang memvalidasi.
    payment_due_at = models.DateTimeField(null=True, blank=True)
    payment_proof = models.ImageField(upload_to=payment_proof_path, null=True, blank=True)
    payment_proof_at = models.DateTimeField(null=True, blank=True)
    payment_verified_by = models.ForeignKey(
        "account.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    payment_verified_at = models.DateTimeField(null=True, blank=True)
    payment_reject_note = models.CharField(max_length=255, blank=True, default="")

    # Nomor urut packing harian, diberikan saat order siap dikemas (lunas / COD).
    packing_date = models.DateField(null=True, blank=True)
    packing_seq = models.PositiveIntegerField(null=True, blank=True)
    packed_at = models.DateTimeField(null=True, blank=True)
    packed_by = models.ForeignKey(
        "account.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    handover_code = models.CharField(max_length=12, blank=True, default="", editable=False)

    # Rute kurir: urutan antar (1 = tujuan berikutnya), dihitung courier.routing.
    route_position = models.PositiveSmallIntegerField(null=True, blank=True)
    # Serah terima: titik GPS saat paket diserahkan & apakah QR/kode pelanggan cocok.
    delivered_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivered_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    handover_verified = models.BooleanField(default=False)
    # COD: uang yang dipegang kurir sampai disetor ke kasir.
    cash_collected = models.PositiveBigIntegerField(default=0)
    remittance = models.ForeignKey(
        "courier.CashRemittance", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    review = models.CharField("Ulasan", max_length=255, blank=True, default="")
    rated_at = models.DateTimeField(null=True, blank=True)

    # ---- Kasir (transaksi offline) ----
    fulfillment = models.CharField(
        max_length=8, choices=Fulfillment.choices, default=Fulfillment.DELIVERY
    )
    # Struk: nomor urut harian (STR-YYMMDD-0001) & token acak untuk struk digital.
    receipt_no = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    receipt_token = models.CharField(max_length=32, unique=True, null=True, blank=True, editable=False)
    # Pembeli tanpa akun (customer = akun "Pelanggan umum").
    buyer_name = models.CharField(max_length=80, blank=True, default="")
    buyer_phone = models.CharField(max_length=20, blank=True, default="")
    discount = models.PositiveBigIntegerField(default=0)
    discount_reason = models.CharField(max_length=160, blank=True, default="")
    discount_by = models.ForeignKey(
        "account.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.PositiveBigIntegerField(default=0)
    cash_received = models.PositiveBigIntegerField(default=0)
    change_given = models.PositiveBigIntegerField(default=0)
    shift = models.ForeignKey(
        "transaction.CashierShift", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        "account.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    void_reason = models.CharField(max_length=255, blank=True, default="")

    _ALLOWED_TRANSITIONS = {
        OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
        OrderStatus.CONFIRMED: {
            OrderStatus.ON_DELIVERY,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
        },
        # ON_DELIVERY -> CONFIRMED hanya lewat return_to_store (paket gagal diantar).
        OrderStatus.ON_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.CONFIRMED},
    }

    # OOP: ENKAPSULASI - resi dibuat Order sendiri; pemanggil (checkout, seed,
    # admin) tidak perlu tahu formatnya.
    def save(self, *args, **kwargs):
        if self._state.adding and not self.tracking_number:
            self.tracking_number = self._unique_tracking_number()
        if self._state.adding and not self.handover_code:
            self.handover_code = new_handover_code()
        super().save(*args, **kwargs)

    @classmethod
    def _unique_tracking_number(cls):
        for _ in range(10):
            candidate = new_tracking_number()
            if not cls.objects.filter(tracking_number=candidate).exists():
                return candidate
        raise PetshopError("Gagal membuat resi unik, coba lagi.")

    @property
    def is_open(self):
        return self.order_status in self._ALLOWED_TRANSITIONS

    @property
    def delivery_address(self):
        """Alamat pengiriman order ini (order lama memakai alamat akun pelanggan)."""
        return self.shipping_address or self.customer.address

    @property
    def maps_url(self):
        address = self.delivery_address
        if not address:
            return ""
        return f"https://www.google.com/maps/search/?api=1&query={quote(address)}"

    @property
    def items_total(self):
        return self.total_payment - self.shipping_fee

    @property
    def has_pin(self):
        return self.delivery_latitude is not None and self.delivery_longitude is not None

    @property
    def packing_label(self):
        """'No. 007' (urut per hari); kosong bila belum masuk antrean packing."""
        return f"{self.packing_seq:03d}" if self.packing_seq else ""

    @property
    def awaiting_payment_check(self):
        """Pelanggan sudah kirim bukti transfer, menunggu dicek kasir/admin."""
        return (
            self.payment_status == PaymentStatus.PENDING
            and bool(self.payment_proof)
            and self.order_status != OrderStatus.CANCELLED
        )

    @property
    def can_upload_proof(self):
        return (
            self.payment_method == PaymentMethod.TRANSFER
            and self.payment_status == PaymentStatus.PENDING
            and self.order_status in (OrderStatus.PENDING, OrderStatus.CONFIRMED)
        )

    @property
    def handover_payload(self):
        """Isi QR serah-terima di HP pelanggan (beda dengan resi di label paket)."""
        return f"PSH:{self.tracking_number}:{self.handover_code}"

    # Kunci tautan lacak yang membuka QR serah-terima untuk pembeli tanpa login
    # (pesanan manual lewat kasir). Dikirim lewat WhatsApp, tidak dicetak di label.
    HANDOVER_SALT = "order-handover"

    @property
    def handover_key(self):
        from django.core import signing

        return signing.dumps(self.pk, salt=self.HANDOVER_SALT)

    def check_handover_key(self, key):
        from django.core import signing

        try:
            return signing.loads(key or "", salt=self.HANDOVER_SALT) == self.pk
        except signing.BadSignature:
            return False

    @property
    def shows_handover_qr(self):
        """QR serah-terima hanya berguna selama paket belum diterima."""
        return self.fulfillment == Fulfillment.DELIVERY and self.order_status in (
            OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.ON_DELIVERY
        )

    @property
    def has_delivery_proof(self):
        return bool(self.delivery_photo)

    # OOP: POLIMORFISME  perilaku bergantung pada objek Payment, bukan if-else.
    @property
    def payment_handler(self):
        return get_payment(self.payment_method)

    # OOP: ENKAPSULASI  "kapan order telat bayar" milik Order sendiri,
    # view cukup membaca `order.is_overdue`.
    @property
    def is_overdue(self):
        return (
            self.payment_status == PaymentStatus.PENDING
            and self.payment_handler.can_be_late()
            and self.order_status != OrderStatus.CANCELLED
            and not self.payment_proof
            and self.date < timezone.now() - UNPAID_GRACE
        )

    @property
    def payment_expired(self):
        return (
            self.payment_due_at is not None
            and self.payment_due_at < timezone.now()
            and self.payment_status == PaymentStatus.PENDING
            and not self.payment_proof
            and self.order_status in (OrderStatus.PENDING, OrderStatus.CONFIRMED)
        )

    @classmethod
    def cancel_expired(cls):
        """Batalkan transfer yang lewat batas bayar tanpa bukti; stok dikembalikan.

        Dipanggil dari halaman staf/pelanggan (tanpa cron) dan dari perintah
        `python manage.py cancel_expired_orders`. Mengembalikan jumlah yang dibatalkan.
        """
        from store.models import ActivityLog, Notification

        expired = cls.objects.filter(
            models.Q(payment_proof="") | models.Q(payment_proof__isnull=True),
            payment_method=PaymentMethod.TRANSFER,
            payment_status=PaymentStatus.PENDING,
            order_status__in=(OrderStatus.PENDING, OrderStatus.CONFIRMED),
            payment_due_at__lt=timezone.now(),
        )
        count = 0
        for order in expired.select_related("customer"):
            try:
                order.cancel()
            except InvalidTransition:
                continue
            ActivityLog.record(order, "Dibatalkan otomatis", detail="Lewat batas waktu pembayaran")
            Notification.send(
                order.customer,
                f"Pesanan #{order.pk} dibatalkan",
                "Batas waktu transfer sudah lewat. Silakan pesan ulang bila masih berminat.",
                "/pesanan-saya/",
            )
            count += 1
        return count

    # OOP: ENKAPSULASI dan POLIFORM siap dikirim atau belum ditentukan
    # Order bersama Payment-nya, bukan string "cod"/"paid" di view.
    @property
    def is_ready_to_ship(self):
        return self.order_status == OrderStatus.CONFIRMED and (
            not self.payment_handler.must_be_paid_before_delivery()
            or self.payment_status == PaymentStatus.PAID
        )

    # OOP: ENKAPSULASI  satu-satunya jalan ganti status; aturan transisi
    # tersimpan di _ALLOWED_TRANSITIONS dan tidak boleh dilewati.
    def _move_to(self, new_status):
        if new_status not in self._ALLOWED_TRANSITIONS.get(self.order_status, set()):
            raise InvalidTransition(
                f"Order #{self.pk}: status {OrderStatus(self.order_status).label} tidak bisa diubah ke {OrderStatus(new_status).label}."
            )
        self.order_status = new_status

    @staticmethod
    def _check_courier_free(courier):
        """Kurir yang sedang antar-jemput hewan tidak boleh membawa paket sampai tugas itu selesai."""
        from service.models import ServiceBooking

        trip = ServiceBooking.active_trip(courier)
        if trip is not None:
            raise InvalidTransition(
                f"Kurir sedang antar-jemput hewan (booking #{trip.pk}). Paket bisa dibawa setelah tugas itu selesai."
            )

    # OOP: ENKAPSULASI  admin hanya menugaskan kurir; status tidak berubah.
    # Aturan pembayaran (transfer harus lunas, tunai boleh belum) dijaga di sini.
    def assign_courier(self, courier):
        if courier is None:
            raise InvalidTransition(f"Order #{self.pk}: pilih kurir terlebih dahulu.")
        if self.order_status != OrderStatus.CONFIRMED:
            raise InvalidTransition(
                f"Order #{self.pk}: kurir hanya bisa ditugaskan saat order Dikonfirmasi."
            )
        if not self.is_ready_to_ship:
            raise InvalidTransition(
                f"Order #{self.pk}: transfer harus lunas dulu sebelum kurir ditugaskan."
            )
        self._check_courier_free(courier)
        self.courier = courier
        self.save(update_fields=["courier"])

    # Dipanggil kurir (bukan admin) saat paket mulai diantar.
    def mark_on_delivery(self, courier=None):
        if courier is None and self.courier_id is None:
            raise InvalidTransition(f"Order #{self.pk}: pilih kurir terlebih dahulu.")
        self._check_courier_free(courier or self.courier)  # dicek sebelum kurir dipasang ke order
        if courier is not None:
            self.courier = courier
        if self.order_status == OrderStatus.CONFIRMED and not self.is_ready_to_ship:
            raise InvalidTransition(
                f"Order #{self.pk}: transfer belum lunas, belum bisa dikirim."
            )
        self._move_to(OrderStatus.ON_DELIVERY)
        self.shipped_at = timezone.now()
        self.save(update_fields=["order_status", "courier", "shipped_at"])

    # Kurir wajib melampirkan foto (dijaga form kurir); admin boleh menutup order
    # tanpa foto, jadi `photo` opsional di level model.
    def mark_delivered(self, photo=None, note=""):
        self._move_to(OrderStatus.DELIVERED)
        if self.payment_handler.paid_after_accepted():
            self.payment_status = PaymentStatus.PAID
        self.delivered_at = timezone.now()
        fields = ["order_status", "payment_status", "delivered_at"]
        if photo is not None:
            self.delivery_photo = photo
            fields.append("delivery_photo")
        if note:
            self.delivery_note = note[:255]
            fields.append("delivery_note")
        self.save(update_fields=fields)

    @property
    def is_online(self):
        return self.channel == OrderChannel.ONLINE

    @property
    def is_counter_sale(self):
        """Transaksi kasir yang punya struk (transaksi toko lama tidak punya)."""
        return bool(self.receipt_no)

    @property
    def is_take_away(self):
        return self.fulfillment == Fulfillment.TAKE_AWAY

    @property
    def is_walk_in(self):
        return bool(getattr(self.customer, "is_walk_in", False))

    @property
    def buyer_display(self):
        if self.is_walk_in:
            return self.buyer_name or _("Pelanggan umum")
        return self.customer.name

    @property
    def phone_last4(self):
        """4 digit terakhir nomor WA pemesan, untuk verifikasi halaman lacak tanpa login."""
        phone = self.buyer_phone if self.is_walk_in else self.customer.phone_number
        digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        return digits[-4:] if len(digits) >= 4 else ""

    @property
    def buyer_whatsapp_url(self):
        if not self.is_walk_in:
            return self.customer.whatsapp_url
        number = "".join(ch for ch in self.buyer_phone if ch.isdigit())
        if not number:
            return ""
        return "https://wa.me/" + ("62" + number[1:] if number.startswith("0") else number)

    @property
    def goods_subtotal(self):
        return sum(d.subtotal for d in self.details.all())

    @property
    def services_subtotal(self):
        return sum(line.amount for line in self.service_lines.all())

    @property
    def subtotal_before_discount(self):
        return self.goods_subtotal + self.services_subtotal

    @property
    def status_display(self):
        """'Selesai di kasir' untuk barang yang langsung dibawa pembeli."""
        if self.is_take_away and self.order_status == OrderStatus.DELIVERED:
            return _("Selesai di kasir")
        return self.get_order_status_display()

    @property
    def is_voided(self):
        return self.voided_at is not None

    @property
    def is_waiting_confirmation(self):
        return self.order_status == OrderStatus.PENDING

    # Admin/kasir menerima pesanan online: Menunggu Konfirmasi -> Dikonfirmasi.
    def confirm(self, user):
        if self.order_status != OrderStatus.PENDING:
            raise InvalidTransition(f"Order #{self.pk} sudah dikonfirmasi atau diproses.")
        self._move_to(OrderStatus.CONFIRMED)
        self.confirmed_at = timezone.now()
        fields = ["order_status", "confirmed_at"]
        if self.admin_id is None:
            self.admin = user
            fields.append("admin")
        self.save(update_fields=fields)
        self.queue_for_packing()

    @transaction.atomic
    def queue_for_packing(self):
        """Beri nomor urut packing harian begitu order siap dikemas (dikonfirmasi + lunas/COD)."""
        if self.packing_seq or not self.is_ready_to_ship:
            return False
        today = timezone.localdate()
        last = (
            Order.objects.select_for_update()
            .filter(packing_date=today)
            .aggregate(m=models.Max("packing_seq"))["m"]
            or 0
        )
        self.packing_date = today
        self.packing_seq = last + 1
        self.save(update_fields=["packing_date", "packing_seq"])
        return True

    def mark_packed(self, user):
        if self.order_status != OrderStatus.CONFIRMED or not self.packing_seq:
            raise InvalidTransition(f"Order #{self.pk} belum masuk antrean packing.")
        self.packed_at = timezone.now()
        self.packed_by = user
        self.save(update_fields=["packed_at", "packed_by"])

    # ---- Kurir: ambil paket (scan label), serah terima (scan QR pelanggan), kendala ----

    @classmethod
    def cash_on_hand(cls, courier):
        """Order COD yang uangnya masih dipegang kurir (belum disetor)."""
        return cls.objects.filter(courier=courier, cash_collected__gt=0, remittance__isnull=True)

    @transaction.atomic
    def pickup_by(self, courier):
        """Kurir memindai QR label di toko: paket berangkat (Dalam Pengiriman)."""
        from store.models import StoreSettings

        if self.order_status != OrderStatus.CONFIRMED:
            raise InvalidTransition(
                f"Order #{self.pk} berstatus {OrderStatus(self.order_status).label}, tidak bisa diambil."
            )
        if not self.is_ready_to_ship or not self.packing_seq:
            raise InvalidTransition(f"Order #{self.pk} belum siap dikirim (belum lunas / belum masuk antrean packing).")
        if self.courier_id and self.courier_id != courier.pk:
            raise InvalidTransition(f"Order #{self.pk} sudah ditugaskan ke kurir lain.")
        limit = StoreSettings.current().max_packages_per_courier
        carrying = Order.objects.filter(courier=courier, order_status=OrderStatus.ON_DELIVERY).count()
        if carrying >= limit:
            raise InvalidTransition(f"Anda sudah membawa {carrying} paket (maks. {limit} per rute).")
        if not self.packed_at:
            self.packed_at = timezone.now()
            self.save(update_fields=["packed_at"])
        self.mark_on_delivery(courier)

    def check_handover_code(self, scanned):
        """Terima isi QR ('PSH:<resi>:<kode>') atau kode 8 huruf yang dibacakan pelanggan."""
        raw = (scanned or "").strip().upper()
        if raw.startswith("PSH:"):
            parts = raw.split(":")
            if len(parts) != 3 or parts[1] != (self.tracking_number or ""):
                return False
            raw = parts[2]
        raw = "".join(ch for ch in raw if ch.isalnum())
        return bool(self.handover_code) and secrets.compare_digest(raw, self.handover_code)

    @transaction.atomic
    def handover(self, courier, code, photo, lat=None, lng=None, cash_received=False):
        """Serah terima: QR/kode pelanggan cocok + foto paket di tangan penerima -> Terkirim."""
        if self.courier_id != courier.pk:
            raise InvalidTransition(f"Order #{self.pk} bukan paket Anda.")
        if self.order_status != OrderStatus.ON_DELIVERY:
            raise InvalidTransition(f"Order #{self.pk} tidak sedang diantar.")
        if not self.check_handover_code(code):
            raise InvalidTransition("QR / kode serah-terima tidak cocok dengan paket ini.")
        if photo is None:
            raise InvalidTransition("Foto paket di tangan penerima wajib diambil.")
        cod = self.payment_method == PaymentMethod.CASH and self.payment_status != PaymentStatus.PAID
        if cod and not cash_received:
            raise InvalidTransition(f"Pastikan uang tunai Rp {self.total_payment:,} sudah diterima.".replace(",", "."))
        self.mark_delivered(photo=photo)
        self.handover_verified = True
        self.delivered_latitude = lat
        self.delivered_longitude = lng
        self.route_position = None
        fields = ["handover_verified", "delivered_latitude", "delivered_longitude", "route_position"]
        if cod:
            self.cash_collected = self.total_payment
            fields.append("cash_collected")
        self.save(update_fields=fields)

    @transaction.atomic
    def return_to_store(self, courier, note, photo=None):
        """Paket gagal diantar (penerima tidak ada, alamat salah): kembali ke antrean toko."""
        if self.courier_id != courier.pk or self.order_status != OrderStatus.ON_DELIVERY:
            raise InvalidTransition(f"Order #{self.pk} tidak sedang Anda antar.")
        if not (note or "").strip():
            raise InvalidTransition("Tulis kendalanya supaya admin bisa menghubungi pelanggan.")
        self._move_to(OrderStatus.CONFIRMED)
        self.courier = None
        self.shipped_at = None
        self.route_position = None
        self.save(update_fields=["order_status", "courier", "shipped_at", "route_position"])

    def rate(self, customer, stars, review=""):
        if self.customer_id != customer.pk:
            raise InvalidTransition("Pesanan ini bukan milik Anda.")
        if self.order_status != OrderStatus.DELIVERED:
            raise InvalidTransition("Ulasan bisa diberikan setelah pesanan sampai.")
        if self.rating:
            raise InvalidTransition("Pesanan ini sudah diberi ulasan.")
        if stars not in range(1, 6):
            raise InvalidTransition("Pilih 1 sampai 5 bintang.")
        self.rating = stars
        self.review = (review or "").strip()[:255]
        self.rated_at = timezone.now()
        self.save(update_fields=["rating", "review", "rated_at"])

    def stops_before(self):
        """Berapa alamat lain yang dikunjungi kurir sebelum alamat order ini."""
        if self.order_status != OrderStatus.ON_DELIVERY or not self.route_position:
            return None
        return Order.objects.filter(
            courier_id=self.courier_id,
            order_status=OrderStatus.ON_DELIVERY,
            route_position__lt=self.route_position,
        ).count()

    def submit_payment_proof(self, customer, photo):
        if self.customer_id != customer.pk:
            raise InvalidTransition("Pesanan ini bukan milik Anda.")
        if not self.can_upload_proof:
            raise InvalidTransition(f"Pesanan #{self.pk} tidak sedang menunggu transfer.")
        self.payment_proof = photo
        self.payment_proof_at = timezone.now()
        self.payment_reject_note = ""
        self.save(update_fields=["payment_proof", "payment_proof_at", "payment_reject_note"])

    def verify_payment(self, user):
        """Kasir/admin mencocokkan bukti dengan mutasi rekening lalu menyetujui."""
        self.mark_paid()
        self.payment_verified_by = user
        self.payment_verified_at = timezone.now()
        self.save(update_fields=["payment_verified_by", "payment_verified_at"])
        self.queue_for_packing()

    def reject_payment(self, user, note):
        note = (note or "").strip()
        if not note:
            raise InvalidTransition("Tulis alasan penolakan supaya pelanggan tahu yang harus diperbaiki.")
        if not self.awaiting_payment_check:
            raise InvalidTransition(f"Order #{self.pk} tidak punya bukti transfer yang menunggu dicek.")
        self.payment_proof.delete(save=False)
        self.payment_proof = None
        self.payment_reject_note = note[:255]
        # Beri waktu lagi supaya pelanggan sempat mengirim ulang.
        from store.models import StoreSettings

        extra = timedelta(hours=StoreSettings.current().payment_deadline_hours)
        self.payment_due_at = max(self.payment_due_at or timezone.now(), timezone.now() + extra)
        self.save(update_fields=["payment_proof", "payment_reject_note", "payment_due_at"])

    def cancel_by_customer(self, customer):
        """Pelanggan hanya boleh membatalkan pesanannya selama belum dikonfirmasi."""
        if self.customer_id != customer.pk:
            raise InvalidTransition("Pesanan ini bukan milik Anda.")
        if self.order_status != OrderStatus.PENDING:
            raise InvalidTransition(
                f"Pesanan #{self.pk} sudah diproses toko, hubungi admin untuk pembatalan."
            )
        self.cancel()

    # OOP: ENKAPSULASI - satu pintu pesanan online dari pelanggan yang login.
    # Harga & stok diambil dari database (bukan dari keranjang di browser).
    @classmethod
    @transaction.atomic
    def place_online(
        cls,
        customer,
        lines,
        payment_method,
        note="",
        address=None,
        client_token=None,
        expected_total=None,
        location=None,
    ):
        """lines: [(product_id, jumlah), ...] dari keranjang pelanggan.

        client_token yang sama mengembalikan order yang sudah ada (anti dobel
        klik). expected_total (total yang dilihat pelanggan) dibandingkan dengan
        total hitungan server; bila beda, pesanan dibatalkan dengan PriceChanged.
        """
        client_token = (client_token or "").strip()[:64] or None
        if client_token:
            existing = cls.objects.filter(
                customer=customer, client_token=client_token
            ).first()
            if existing is not None:
                existing.replayed = True
                return existing
        if payment_method not in ONLINE_PAYMENT_METHODS:
            raise CheckoutError("Metode pembayaran tidak valid.")
        wanted = {}
        for product_id, qty in lines:
            try:
                product_id, qty = int(product_id), int(qty)
            except (TypeError, ValueError):
                raise CheckoutError("Data keranjang tidak valid.")
            if qty <= 0:
                continue
            wanted[product_id] = wanted.get(product_id, 0) + qty
        if not wanted:
            raise CheckoutError("Keranjang Anda kosong.")
        for product_id, qty in wanted.items():
            if qty > ONLINE_MAX_QTY:
                raise CheckoutError(
                    f"Maksimal {ONLINE_MAX_QTY} pcs per barang untuk pesanan online."
                )

        products = Product.objects.sellable().in_bulk(list(wanted))
        missing = [pk for pk in wanted if pk not in products]
        if missing:
            raise CheckoutError(
                "Sebagian barang di keranjang sudah tidak dijual. "
                "Hapus barang tersebut dari keranjang lalu coba lagi."
            )

        from store.models import StoreSettings

        store = StoreSettings.current()
        pin = {}
        shipping_fee = 0
        if location is not None:
            lat, lng = location
            distance = store.distance_km(lat, lng)
            if not store.can_deliver_to(distance):
                raise CheckoutError(
                    f"Alamat berjarak {distance:.1f} km dari toko, di luar jangkauan antar "
                    f"(maks. {store.max_delivery_km} km)."
                )
            shipping_fee = store.shipping_fee(distance)
            pin = {
                "delivery_latitude": lat,
                "delivery_longitude": lng,
                "delivery_distance_km": round(distance, 2),
            }
        due = None
        if payment_method == PaymentMethod.TRANSFER:
            due = timezone.now() + timedelta(hours=store.payment_deadline_hours)

        order = cls.objects.create(
            admin=None,
            customer=customer,
            channel=OrderChannel.ONLINE,
            shipping_fee=shipping_fee,
            payment_due_at=due,
            **pin,
            order_status=OrderStatus.PENDING,
            payment_method=payment_method,
            customer_note=(note or "").strip()[:255],
            shipping_address=(address if address is not None else customer.address)[:255],
            client_token=client_token,
        )
        total = 0
        for product_id, qty in wanted.items():
            product = products[product_id]
            # InsufficientStock (PetshopError) membatalkan seluruh pesanan.
            product.apply_mutation(
                MutationType.OUT, qty, user=customer, note=f"Order online #{order.pk}"
            )
            subtotal = product.selling_price * qty
            OrderDetail.objects.create(
                transaction=order,
                product=product,
                quantity=qty,
                unit_price=product.selling_price,
                subtotal=subtotal,
            )
            total += subtotal
        total += shipping_fee
        if expected_total is not None and int(expected_total) != total:
            # Raise di dalam atomic: order & mutasi stok di atas ikut di-rollback.
            raise PriceChanged(total)
        order.total_payment = total
        order.save(update_fields=["total_payment"])
        return order

    def mark_paid(self):
        if self.order_status == OrderStatus.CANCELLED:
            raise InvalidTransition(f"Order #{self.pk} sudah dibatalkan.")
        self.payment_status = PaymentStatus.PAID
        self.save(update_fields=["payment_status"])
        self.queue_for_packing()

    @transaction.atomic
    def cancel(self):
        # Baca ulang status dengan kunci baris: dua pembatalan bersamaan tidak
        # boleh mengembalikan stok dua kali.
        self.order_status = (
            Order.objects.select_for_update()
            .values_list("order_status", flat=True)
            .get(pk=self.pk)
        )
        self._move_to(OrderStatus.CANCELLED)
        self.save(update_fields=["order_status"])
        for detail in self.details.select_related("product"):
            detail.product.apply_mutation(
                MutationType.IN,
                detail.quantity,
                note=f"Order #{self.pk} dibatalkan, stok dikembalikan",
            )

    class Meta:
        verbose_name = "order"
        verbose_name_plural = "order"


class OrderDetail(models.Model):
    transaction = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="details"
    )

    product = models.ForeignKey("product.Product", on_delete=models.PROTECT)

    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveBigIntegerField()
    subtotal = models.PositiveBigIntegerField()

    class Meta:
        verbose_name = "item order"
        verbose_name_plural = "item order"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="orderdetail_quantity_gt_0",
            )
        ]


class Cart(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    @property
    def goods_total(self):
        return sum(item.subtotal for item in self.items.select_related("product"))

    @property
    def services_total(self):
        return sum(line.booking.total_price for line in self.services.select_related("booking__service"))

    @property
    def total(self):
        return self.goods_total + self.services_total

    @property
    def is_empty(self):
        return not self.items.exists() and not self.services.exists()

    def add_service(self, booking):
        """Tambahkan tagihan booking grooming ke transaksi kasir."""
        from .pos import ensure_booking_payable

        ensure_booking_payable(booking)
        line, _created = self.services.get_or_create(booking=booking)
        return line

    # OOP: ENKAPSULASI - aturan tambah item (cek stok, naikkan jumlah) milik
    # Cart; view cukup memanggil `cart.add(product)`.
    def add(self, product):
        """Tambah 1 unit. InsufficientStock bila stok habis / sudah semua di cart."""
        if product.stock <= 0:
            raise InsufficientStock(product, 1)
        item, created = self.items.get_or_create(product=product)
        if not created:
            if item.quantity >= product.stock:
                raise InsufficientStock(product, item.quantity + 1)
            item.quantity += 1
            item.save(update_fields=["quantity"])
        return item

    def set_quantity(self, item_id, quantity):
        """Atur jumlah item cart. quantity <= 0 menghapus item."""
        item = self.items.select_related("product").get(pk=item_id)
        if quantity <= 0:
            item.delete()
            return None
        if quantity > item.product.stock:
            raise InsufficientStock(item.product, quantity)
        item.quantity = quantity
        item.save(update_fields=["quantity"])
        return item

    # OOP: ENKAPSULASI - proses checkout (stok, detail, total) satu transaksi atomik.
    @transaction.atomic
    def checkout(self, customer, admin, payment_method, courier=None):
        """Ubah cart jadi Order. Gagal di item mana pun = semua di-rollback."""
        items = list(self.items.select_related("product"))
        if not items:
            raise CheckoutError("Belum ada item di order.")
        if (
            courier is not None
            and get_payment(payment_method).must_be_paid_before_delivery()
        ):
            raise CheckoutError(
                "Order transfer: kurir bisa ditugaskan setelah pembayaran lunas."
            )

        order = Order.objects.create(
            admin=admin,
            courier=courier,
            customer=customer,
            order_status=OrderStatus.CONFIRMED,
            payment_method=payment_method,
            shipping_address=customer.address,
        )
        total = 0
        for item in items:
            if not item.product.isSellable:
                raise CheckoutError(f"'{item.product.name}' tidak dijual.")
            item.product.apply_mutation(
                MutationType.OUT,
                item.quantity,
                user=admin,
                note=f"Order #{order.pk}",
            )
            OrderDetail.objects.create(
                transaction=order,
                product=item.product,
                quantity=item.quantity,
                unit_price=item.product.selling_price,
                subtotal=item.subtotal,
            )
            total += item.subtotal

        order.total_payment = total
        order.save(update_fields=["total_payment"])
        order.queue_for_packing()
        self.delete()
        return order


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ["cart", "product"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="cartitem_quantity_gt_0",
            )
        ]

    @property
    def subtotal(self):
        return (self.product.selling_price or 0) * self.quantity


class CartService(models.Model):
    """Tagihan booking grooming yang akan dibayar di transaksi kasir."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="services")
    booking = models.ForeignKey("service.ServiceBooking", on_delete=models.CASCADE, related_name="+")

    class Meta:
        unique_together = ["cart", "booking"]


class OrderPayment(models.Model):
    """Satu baris pembayaran di kasir; bayar campuran = beberapa baris."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    amount = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["pk"]
        verbose_name = "pembayaran kasir"
        verbose_name_plural = "pembayaran kasir"


class OrderServiceLine(models.Model):
    """Biaya layanan grooming yang dibayar lewat transaksi kasir."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="service_lines")
    booking = models.ForeignKey(
        "service.ServiceBooking", on_delete=models.PROTECT, related_name="payment_lines"
    )
    description = models.CharField(max_length=160)
    amount = models.PositiveBigIntegerField()

    class Meta:
        ordering = ["pk"]
        verbose_name = "pembayaran layanan"
        verbose_name_plural = "pembayaran layanan"


class ShiftStatus(models.TextChoices):
    OPEN = "BUKA", _("Buka")
    CLOSED = "TUTUP", _("Tutup")


class CashierShift(models.Model):
    """Buka/tutup kasir: modal awal laci, uang yang seharusnya ada, hasil hitung, selisih."""

    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shifts")
    status = models.CharField(max_length=5, choices=ShiftStatus.choices, default=ShiftStatus.OPEN, db_index=True)
    opened_at = models.DateTimeField(default=timezone.now)
    opening_cash = models.PositiveBigIntegerField(default=0)
    closed_at = models.DateTimeField(null=True, blank=True)
    expected_cash = models.BigIntegerField(null=True, blank=True)
    counted_cash = models.PositiveBigIntegerField(null=True, blank=True)
    difference = models.BigIntegerField(null=True, blank=True)
    close_note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-opened_at", "-pk"]
        verbose_name = "shift kasir"
        verbose_name_plural = "shift kasir"
        constraints = [
            models.UniqueConstraint(
                fields=["cashier"], condition=models.Q(status="BUKA"), name="one_open_shift_per_cashier"
            )
        ]

    def __str__(self):
        return f"Shift #{self.pk} {self.cashier}"

    @classmethod
    def current(cls, user):
        return cls.objects.filter(cashier=user, status=ShiftStatus.OPEN).first()

    @property
    def is_open(self):
        return self.status == ShiftStatus.OPEN

    def _window(self):
        return self.opened_at, self.closed_at or timezone.now()

    def summary(self):
        """Ringkasan uang shift ini (dihitung dari transaksi, retur, dan setoran COD)."""
        from courier.models import CashRemittance, RemittanceStatus

        payments = OrderPayment.objects.filter(order__shift=self).exclude(
            order__order_status=OrderStatus.CANCELLED
        )
        by_method = {m: 0 for m in COUNTER_PAYMENT_METHODS}
        for row in payments.values("method").annotate(total=models.Sum("amount")):
            by_method[row["method"]] = row["total"] or 0
        orders = self.orders.exclude(order_status=OrderStatus.CANCELLED)
        start, end = self._window()
        remitted = (
            CashRemittance.objects.filter(
                received_by=self.cashier, status=RemittanceStatus.RECEIVED,
                received_at__gte=start, received_at__lte=end,
            ).aggregate(t=models.Sum("received_amount"))["t"]
            or 0
        )
        refunds = (
            ReturnRequest.objects.filter(
                refund_shift=self, status=ReturnStatus.APPROVED, refund_method=PaymentMethod.CASH
            ).aggregate(t=models.Sum("refund_amount"))["t"]
            or 0
        )
        cash_sales = by_method[PaymentMethod.CASH]
        return {
            "by_method": [(PaymentMethod(m).label, m, by_method[m]) for m in COUNTER_PAYMENT_METHODS],
            "orders": orders.count(),
            "total": sum(by_method.values()),
            "discount": orders.aggregate(t=models.Sum("discount"))["t"] or 0,
            "voided": self.orders.filter(order_status=OrderStatus.CANCELLED).count(),
            "cash_sales": cash_sales,
            "noncash_sales": sum(by_method.values()) - cash_sales,
            "remitted": remitted,
            "refunds": refunds,
            "expected_cash": self.opening_cash + cash_sales + remitted - refunds,
        }

    @transaction.atomic
    def close(self, counted_cash, note=""):
        from store.models import ActivityLog, Notification
        from account.models import ADMIN_ROLES

        if not self.is_open:
            raise InvalidTransition("Shift ini sudah ditutup.")
        if counted_cash is None or counted_cash < 0:
            raise InvalidTransition("Isi jumlah uang tunai yang ada di laci.")
        expected = self.summary()["expected_cash"]
        difference = counted_cash - expected
        note = (note or "").strip()
        if difference and not note:
            raise InvalidTransition("Ada selisih uang: tulis catatan penyebabnya.")
        self.status = ShiftStatus.CLOSED
        self.closed_at = timezone.now()
        self.expected_cash = expected
        self.counted_cash = counted_cash
        self.difference = difference
        self.close_note = note[:255]
        self.save()
        ActivityLog.record(self, "Kasir ditutup", actor=self.cashier,
                           detail=f"Seharusnya Rp {expected:,}, dihitung Rp {counted_cash:,}".replace(",", "."))
        if difference:
            Notification.to_staff(
                ADMIN_ROLES,
                f"Selisih kas {self.cashier.display_name}",
                f"Shift #{self.pk}: selisih Rp {difference:,}. {note}".replace(",", "."),
                "/staff/admin/laporan-kasir/",
            )
        return self


class HeldSale(models.Model):
    """Transaksi kasir yang diparkir (stok belum dikurangi sampai dibayar)."""

    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="held_sales")
    label = models.CharField(max_length=60, blank=True, default="")
    lines = models.JSONField(default=list)  # [[product_id, jumlah], ...]
    bookings = models.JSONField(default=list)  # [booking_id, ...]
    total = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "transaksi diparkir"
        verbose_name_plural = "transaksi diparkir"

    @property
    def item_count(self):
        return sum(qty for _pid, qty in self.lines) + len(self.bookings)


class ReturnStatus(models.TextChoices):
    PENDING = "MENUNGGU", _("Menunggu persetujuan")
    APPROVED = "DISETUJUI", _("Disetujui")
    REJECTED = "DITOLAK", _("Ditolak")


class ReturnRequest(models.Model):
    """Retur/tukar barang: diajukan kasir, disetujui admin (stok kembali, uang dikembalikan)."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="returns")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    requested_at = models.DateTimeField(default=timezone.now)
    reason = models.CharField(max_length=255)
    refund_method = models.CharField(max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    refund_amount = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=10, choices=ReturnStatus.choices, default=ReturnStatus.PENDING, db_index=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True, default="")
    # Retur tunai mengurangi uang di laci shift ini.
    refund_shift = models.ForeignKey(
        CashierShift, on_delete=models.SET_NULL, null=True, blank=True, related_name="refunds"
    )

    class Meta:
        ordering = ["-requested_at", "-pk"]
        verbose_name = "retur"
        verbose_name_plural = "retur"


class ReturnLine(models.Model):
    request = models.ForeignKey(ReturnRequest, on_delete=models.CASCADE, related_name="lines")
    detail = models.ForeignKey(OrderDetail, on_delete=models.PROTECT, related_name="return_lines")
    quantity = models.PositiveIntegerField()
    amount = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["pk"]
