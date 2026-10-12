from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
from product.models import Product, MutationType
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
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class OrderStatus(models.TextChoices):
    PENDING = "PENDING"
    ON_DELIVERY = "ON DELIVERY"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Order(models.Model):
    admin = models.ForeignKey("account.User", on_delete=models.PROTECT)
    courir = models.ForeignKey(
        "account.User",
        on_delete=models.PROTECT,
        related_name="orders_as_courir",
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(
        "account.Customer", on_delete=models.PROTECT, related_name="orders"
    )
    order_status = models.CharField(
        max_length=20, choices=OrderStatus.choices, null=False, blank=False
    )
    payment_method = models.CharField(max_length=50, choices=PaymentMethod.choices)
    payment_status = models.CharField(
        max_length=50, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    total_payment = models.PositiveBigIntegerField(default=0)
    date = models.DateTimeField(default=timezone.now)

    _ALLOWED_TRANSITIONS = {
        OrderStatus.PENDING: {
            OrderStatus.ON_DELIVERY,
            OrderStatus.SUCCESS,
            OrderStatus.FAILED,
        },
        OrderStatus.ON_DELIVERY: {OrderStatus.SUCCESS, OrderStatus.FAILED},
    }

    def _move_to(self, new_status):
        if new_status not in self._ALLOWED_TRANSITIONS.get(self.order_status, set()):
            raise InvalidTransition(
                f"Order #{self.pk}: {self.order_status} tidak bisa ke {new_status}."
            )
        self.order_status = new_status

    def mark_on_delivery(self):
        self._move_to(OrderStatus.ON_DELIVERY)
        self.save(update_fields=["order_status"])

    def mark_success(self):
        self._move_to(OrderStatus.SUCCESS)
        self.payment_status = PaymentStatus.SUCCESS
        self.save(update_fields=["order_status", "payment_status"])

    @transaction.atomic
    def mark_failed(self):
        self._move_to(OrderStatus.FAILED)
        self.payment_status = PaymentStatus.FAILED
        self.save(update_fields=["order_status", "payment_status"])
        for detail in self.details.select_related("product"):
            if detail.product is not None:
                detail.product.apply_mutation(
                    MutationType.IN,
                    detail.quantity,
                    note=f"Order #{self.pk} gagal, stok dikembalikan",
                )


class OrderDetail(models.Model):
    transaction = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="details"
    )

    product = models.ForeignKey(
        "product.Product", on_delete=models.PROTECT, null=True, blank=True
    )

    quantity = models.PositiveIntegerField()
    subtotal = models.PositiveBigIntegerField()


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total(self):
        return sum(item.subtotal for item in self.items.select_related("product"))

    @transaction.atomic
    def checkout(self, customer, admin, payment_method, courier=None):
        """Ubah cart jadi Order. Gagal di item mana pun = semua di-rollback."""
        items = list(self.items.select_related("product"))
        if not items:
            raise CheckoutError("Belum ada item di order.")

        order = Order.objects.create(
            admin=admin,
            courir=courier,
            customer=customer,
            order_status=OrderStatus.PENDING,
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

    @property
    def subtotal(self):
        return (self.product.selling_price or 0) * self.quantity
