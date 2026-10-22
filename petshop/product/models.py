from abc import ABC, abstractmethod

from django.db import models, transaction
from django.utils import timezone
from common.exceptions import PetshopError
from common.models import TimeStampedModel


class Category(models.Model):
    FOOD = "MAKANAN"
    EQUIPMENT = "PERLENGKAPAN"
    ACCESSORIES = "AKSESORIS"
    HEALTHCARE = "KESEHATAN"
    TOYS = "MAINAN"

    CATEGORY_CHOICES = [
        (FOOD, "Makanan"),
        (EQUIPMENT, "Perlengkapan"),
        (ACCESSORIES, "Aksesori"),
        (HEALTHCARE, "Kesehatan"),
        (TOYS, "Mainan"),
    ]

    name = models.CharField(max_length=64, choices=CATEGORY_CHOICES, unique=True)

    def __str__(self):
        return self.get_name_display()


class PetType(models.TextChoices):
    ALL = "SEMUA", "Semua hewan"
    CAT = "KUCING", "Kucing"
    DOG = "ANJING", "Anjing"
    BIRD = "BURUNG", "Burung"
    RABBIT = "KELINCI", "Kelinci"
    FISH = "IKAN", "Ikan"
    HAMSTER = "HAMSTER", "Hamster"


class ProductCondition(models.TextChoices):
    NEW = "BARU", "Baru"
    USED = "BEKAS", "Bekas"


class MutationType(models.TextChoices):
    IN = "MASUK", "Stok Masuk"
    OUT = "KELUAR", "Stok Keluar"


LOW_STOCK_THRESHOLD = 10  # stok 1..10 dianggap menipis, 0 = habis


# OOP: PEWARISAN - InsufficientStock mewarisi PetshopError (hierarki exception).
class InsufficientStock(PetshopError):
    def __init__(self, product, requested):
        self.product = product
        self.requested = requested
        super().__init__(
            f"Stok '{product.name}' tidak cukup. Stok saat ini: {product.stock}"
        )


# OOP: ABSTRAKSI - StockMovement hanya menyatakan "mutasi stok harus bisa
# menghitung stok baru"; rumusnya diserahkan ke StockIn / StockOut.
class StockMovement(ABC):
    code = None

    @abstractmethod
    def apply(self, product, quantity) -> int: ...


# OOP: PEWARISAN + POLIMORFISME - StockIn dan StockOut punya apply() yang sama
# namanya tapi beda hasil; Product.apply_mutation tidak perlu if-else jenis mutasi.
class StockIn(StockMovement):
    code = MutationType.IN

    def apply(self, product, quantity):
        return product.stock + quantity


class StockOut(StockMovement):
    code = MutationType.OUT

    def apply(self, product, quantity):
        if quantity > product.stock:
            raise InsufficientStock(product, quantity)
        return product.stock - quantity


MOVEMENT_REGISTRY = {cls.code: cls() for cls in (StockIn, StockOut)}


def get_movement(code):
    try:
        return MOVEMENT_REGISTRY[code]
    except KeyError:
        raise ValueError(f"Jenis mutasi '{code}' tidak dikenal.")


class ProductQuerySet(models.QuerySet):
    def sellable(self):
        return self.filter(is_active=True, selling_price__isnull=False)


# OOP: PEWARISAN - Product mewarisi TimeStampedModel (created_at, updated_at).
class Product(TimeStampedModel):
    objects = ProductQuerySet.as_manager()

    category = models.ForeignKey(Category, null=False, on_delete=models.PROTECT)
    name = models.CharField(max_length=255, null=False, blank=False)
    purchase_price = models.PositiveBigIntegerField(null=False, blank=False)
    selling_price = models.PositiveBigIntegerField(null=True, blank=True)
    stock = models.PositiveIntegerField(null=False, default=0)
    pet_type = models.CharField(
        max_length=16, choices=PetType.choices, default=PetType.ALL
    )
    condition = models.CharField(
        max_length=8, choices=ProductCondition.choices, default=ProductCondition.NEW
    )
    is_active = models.BooleanField(default=True)

    photo = models.ImageField(upload_to="products", null=True, blank=True)

    @property
    def isSellable(self):
        return self.is_active and self.selling_price is not None

    # OOP: ENKAPSULASI - info turunan dihitung oleh Product sendiri,
    # view tidak perlu menempelkan atribut manual.
    @property
    def stock_state(self):
        if self.stock == 0:
            return "empty"
        return "low" if self.stock <= LOW_STOCK_THRESHOLD else "ok"

    @property
    def margin(self):
        if self.selling_price is None:
            return None
        return self.selling_price - self.purchase_price

    # OOP: ENKAPSULASI - pencatatan stok awal milik Product, bukan view.
    def record_initial_stock(self, user=None):
        """Catat stok awal (saat produk baru dibuat) ke riwayat mutasi."""
        if self.stock > 0:
            return StockMutation.objects.create(
                product=self,
                mutationType=MutationType.IN,
                quantity=self.stock,
                note="Stok awal saat produk dibuat",
                createdBy=user,
            )

    # OOP: ENKAPSULASI + POLIMORFISME - semua perubahan stok lewat sini;
    # rumus stok dipilih lewat get_movement(...).apply(), bukan if-else.
    def apply_mutation(self, mutation_type, quantity, user=None, note=""):
        """Satu-satunya jalan ubah stok: kunci baris, cek, update, catat mutasi."""
        if quantity <= 0:
            raise ValueError("Jumlah mutasi harus lebih dari 0.")
        with transaction.atomic():
            locked = Product.objects.select_for_update().get(pk=self.pk)
            locked.stock = get_movement(mutation_type).apply(locked, quantity)
            locked.save(update_fields=["stock", "updated_at"])
            self.stock = locked.stock
            return StockMutation.objects.create(
                product=locked,
                mutationType=mutation_type,
                quantity=quantity,
                note=note,
                createdBy=user,
            )

    def __str__(self):
        return self.name


class StockMutation(models.Model):
    product = models.ForeignKey(
        Product, null=False, on_delete=models.PROTECT, related_name="mutations"
    )
    mutationType = models.CharField(
        max_length=8, choices=MutationType.choices, null=False
    )
    quantity = models.PositiveIntegerField(null=False)
    date = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=255, default="", blank=True)
    createdBy = models.ForeignKey(
        "account.User", null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="stockmutation_quantity_gt_0",
            )
        ]

    def __str__(self):
        return f"{self.product.name} {self.mutationType} {self.quantity}"
