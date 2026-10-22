from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from product.models import Product, MutationType, InsufficientStock
from common.exceptions import PetshopError
from common.models import TimeStampedModel
from abc import ABC, abstractmethod


UNPAID_GRACE = timedelta(hours=1)  # batas toleransi transfer belum dibayar


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
    CONFIRMED = "DIKONFIRMASI", "Dikonfirmasi"
    ON_DELIVERY = "DALAM_PENGIRIMAN", "Dalam Pengiriman"
    DELIVERED = "TERKIRIM", "Terkirim"
    CANCELLED = "DIBATALKAN", "Dibatalkan"


class Order(models.Model):
    admin = models.ForeignKey("account.User", on_delete=models.PROTECT)
    courier = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="orders_as_courier",
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(
        "account.Customer", on_delete=models.PROTECT, related_name="orders"
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

    _ALLOWED_TRANSITIONS = {
        OrderStatus.CONFIRMED: {
            OrderStatus.ON_DELIVERY,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
        },
        OrderStatus.ON_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    }

    @property
    def is_open(self):
        return self.order_status in self._ALLOWED_TRANSITIONS

    # OOP: POLIMORFISME - perilaku bergantung pada objek Payment, bukan if-else.
    @property
    def payment_handler(self):
        return get_payment(self.payment_method)

    # OOP: ENKAPSULASI - aturan "kapan order telat bayar" milik Order sendiri,
    # view cukup membaca `order.is_overdue`.
    @property
    def is_overdue(self):
        return (
            self.payment_status == PaymentStatus.PENDING
            and self.payment_handler.can_be_late()
            and self.order_status != OrderStatus.CANCELLED
            and self.date < timezone.now() - UNPAID_GRACE
        )

    # OOP: ENKAPSULASI + POLIMORFISME - siap dikirim atau belum ditentukan
    # Order bersama Payment-nya, bukan string "cod"/"paid" di view.
    @property
    def is_ready_to_ship(self):
        return self.order_status == OrderStatus.CONFIRMED and (
            not self.payment_handler.must_be_paid_before_delivery()
            or self.payment_status == PaymentStatus.PAID
        )

    # OOP: ENKAPSULASI - satu-satunya jalan ganti status; aturan transisi
    # tersimpan di _ALLOWED_TRANSITIONS dan tidak boleh dilewati.
    def _move_to(self, new_status):
        if new_status not in self._ALLOWED_TRANSITIONS.get(self.order_status, set()):
            raise InvalidTransition(
                f"Order #{self.pk}: status {OrderStatus(self.order_status).label} tidak bisa diubah ke {OrderStatus(new_status).label}."
            )
        self.order_status = new_status

    # OOP: ENKAPSULASI - admin hanya menugaskan kurir; status tidak berubah.
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
        self.save(update_fields=["order_status", "courier"])

    def mark_delivered(self):
        self._move_to(OrderStatus.DELIVERED)
        if self.payment_handler.paid_after_accepted():
            self.payment_status = PaymentStatus.PAID
        self.save(update_fields=["order_status", "payment_status"])

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
        if courier is not None and get_payment(payment_method).must_be_paid_before_delivery():
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
