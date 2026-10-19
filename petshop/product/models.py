from django.db import models, transaction
from django.utils import timezone


class Category(models.Model):
    FOOD = "FOOD"
    EQUIPMENT = "EQUIPMENT"
    ACCESSORIES = "ACCESSORIES"
    HEALTHCARE = "HEALTHCARE"
    TOYS = "TOYS"
    GROOMING = "GROOMING"

    CATEGORY_CHOICES = [
        (FOOD, "Food"),
        (EQUIPMENT, "Equipment"),
        (ACCESSORIES, "Accessories"),
        (HEALTHCARE, "Healthcare"),
        (TOYS, "Toys"),
        (GROOMING, "Grooming"),
    ]

    name = models.CharField(max_length=64, choices=CATEGORY_CHOICES, unique=True)

    def __str__(self):
        return self.get_name_display()


class PetType(models.TextChoices):
    """Hewan yang dituju produk. ALL = cocok untuk semua hewan (muncul di filter hewan mana pun)."""

    ALL = "ALL", "All pets"
    CAT = "CAT", "Cat"
    DOG = "DOG", "Dog"
    BIRD = "BIRD", "Bird"
    RABBIT = "RABBIT", "Rabbit"
    FISH = "FISH", "Fish"
    HAMSTER = "HAMSTER", "Hamster"


class ProductCondition(models.TextChoices):
    NEW = "NEW", "New"
    USED = "USED", "Used"


class MutationType(models.TextChoices):
    IN = "IN", "Stok Masuk"
    OUT = "OUT", "Stok Keluar"


class InsufficientStock(Exception):
    def __init__(self, product, requested):
        self.product = product
        self.requested = requested
        super().__init__(
            f"Stok '{product.name}' tidak cukup. Stok saat ini: {product.stock}"
        )


class ProductQuerySet(models.QuerySet):
    def sellable(self):
        return self.filter(is_active=True, selling_price__isnull=False)


class Product(models.Model):
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
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    photo = models.ImageField(upload_to="products", null=True, blank=True)

    @property
    def isSellable(self):
        return self.is_active and self.selling_price is not None

    def apply_mutation(self, mutation_type, quantity, user=None, note=""):
        """Satu-satunya jalan ubah stok: kunci baris, cek, update, catat mutasi."""
        if quantity <= 0:
            raise ValueError("Jumlah mutasi harus lebih dari 0.")
        with transaction.atomic():
            locked = Product.objects.select_for_update().get(pk=self.pk)
            if mutation_type == MutationType.OUT:
                if quantity > locked.stock:
                    raise InsufficientStock(locked, quantity)
                locked.stock -= quantity
            else:
                locked.stock += quantity
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
