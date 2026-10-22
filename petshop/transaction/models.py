import secrets
import uuid
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


PAYMENT_REGISTRY = {
    payment_class.code: payment_class() for payment_class in (Cash, Transfer)
}


def get_payment(code):
    return PAYMENT_REGISTRY[code]


class CheckoutError(PetshopError):
    pass


class InvalidTransition(PetshopError):
    pass


class PaymentMethod(models.TextChoices):
    CASH = "TUNAI", "Tunai"
    TRANSFER = "TRANSFER", "Transfer"


class PaymentStatus(models.TextChoices):
    PENDING = "MENUNGGU", "Menunggu"
    PAID = "LUNAS", "Lunas"


class OrderStatus(models.TextChoices):
    PENDING = "MENUNGGU", "Menunggu Konfirmasi"
    CONFIRMED = "DIKONFIRMASI", "Dikonfirmasi"
    ON_DELIVERY = "DALAM_PENGIRIMAN", "Dalam Pengiriman"
    DELIVERED = "TERKIRIM", "Terkirim"
    CANCELLED = "DIBATALKAN", "Dibatalkan"


class OrderChannel(models.TextChoices):
    STORE = "TOKO", "Toko / Kasir"
    ONLINE = "ONLINE", "Online (situs)"


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

    _ALLOWED_TRANSITIONS = {
        OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
        OrderStatus.CONFIRMED: {
            OrderStatus.ON_DELIVERY,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
        },
        OrderStatus.ON_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    }

    # OOP: ENKAPSULASI - resi dibuat Order sendiri; pemanggil (checkout, seed,
    # admin) tidak perlu tahu formatnya.
    def save(self, *args, **kwargs):
        if self._state.adding and not self.tracking_number:
            self.tracking_number = self._unique_tracking_number()
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
            and self.date < timezone.now() - UNPAID_GRACE
        )

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
        self.courier = courier
        self.save(update_fields=["courier"])

    # Dipanggil kurir (bukan admin) saat paket mulai diantar.
    def mark_on_delivery(self, courier=None):
        if courier is not None:
            self.courier = courier
        if self.courier_id is None:
            raise InvalidTransition(f"Order #{self.pk}: pilih kurir terlebih dahulu.")
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
    def is_waiting_confirmation(self):
        return self.order_status == OrderStatus.PENDING

    # Admin/kasir menerima pesanan online: Menunggu Konfirmasi -> Dikonfirmasi.
    def confirm(self, user):
        self._move_to(OrderStatus.CONFIRMED)
        self.confirmed_at = timezone.now()
        fields = ["order_status", "confirmed_at"]
        if self.admin_id is None:
            self.admin = user
            fields.append("admin")
        self.save(update_fields=fields)

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
    def place_online(cls, customer, lines, payment_method, note=""):
        """lines: [(product_id, jumlah), ...] dari keranjang pelanggan."""
        if payment_method not in PaymentMethod.values:
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

        order = cls.objects.create(
            admin=None,
            customer=customer,
            channel=OrderChannel.ONLINE,
            order_status=OrderStatus.PENDING,
            payment_method=payment_method,
            customer_note=(note or "").strip()[:255],
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
        order.total_payment = total
        order.save(update_fields=["total_payment"])
        return order

    def mark_paid(self):
        if self.order_status == OrderStatus.CANCELLED:
            raise InvalidTransition(f"Order #{self.pk} sudah dibatalkan.")
        self.payment_status = PaymentStatus.PAID
        self.save(update_fields=["payment_status"])

    @transaction.atomic
    def cancel(self):
        self._move_to(OrderStatus.CANCELLED)
        self.save(update_fields=["order_status"])
        for detail in self.details.select_related("product"):
            detail.product.apply_mutation(
                MutationType.IN,
                detail.quantity,
                note=f"Order #{self.pk} dibatalkan, stok dikembalikan",
            )


class OrderDetail(models.Model):
    transaction = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="details"
    )

    product = models.ForeignKey("product.Product", on_delete=models.PROTECT)

    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveBigIntegerField()
    subtotal = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="orderdetail_quantity_gt_0",
            )
        ]


class Cart(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.select_related("product"))

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
