from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from product.models import Product, MutationType, InsufficientStock
from account.models import Customer, User


class CheckoutError(Exception):
    pass


class InvalidTransition(Exception):
    pass


class PaymentMethod(models.TextChoices):
    CASH = "CASH"
    TRANSFER = "TRANSFER"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING"
    PAID = "PAID"


class OrderStatus(models.TextChoices):
    CONFIRMED = "CONFIRMED"
    ON_DELIVERY = "ON_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


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

    def _move_to(self, new_status):
        if new_status not in self._ALLOWED_TRANSITIONS.get(self.order_status, set()):
            raise InvalidTransition(
                f"Order #{self.pk}: {self.order_status} tidak bisa ke {new_status}."
            )
        self.order_status = new_status

    def mark_on_delivery(self, courier=None):
        if courier is not None:
            self.courier = courier
        if self.courier_id is None:
            raise InvalidTransition(f"Order #{self.pk}: pilih kurir dulu.")
        self._move_to(OrderStatus.ON_DELIVERY)
        self.save(update_fields=["order_status", "courier"])

    def mark_delivered(self):
        self._move_to(OrderStatus.DELIVERED)
        # CASH dibayar saat barang diterima; TRANSFER dikonfirmasi lewat mark_paid().
        if self.payment_method == PaymentMethod.CASH:
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


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.select_related("product"))

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

    @transaction.atomic
    def checkout(self, customer, admin, payment_method, courier=None):
        """Ubah cart jadi Order. Gagal di item mana pun = semua di-rollback."""
        items = list(self.items.select_related("product"))
        if not items:
            raise CheckoutError("Belum ada item di order.")

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
