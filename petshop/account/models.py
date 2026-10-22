import re
from urllib.parse import quote

from django.apps import apps
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Concat
from django.contrib.auth.models import AbstractUser, UserManager
from abc import abstractmethod, ABC

AVATAR_TONES = 6


# OOP: ABSTRAKSI - RoleBehavior mendefinisikan "apa" yang dimiliki setiap peran
# (dashboard, hak akses, statistik) tanpa isi; tiap peran mengisi sendiri.
class RoleBehavior(ABC):
    code = None
    label = None
    badge_class = ""
    badge_icon = ""
    summary_icon = ""

    @property
    @abstractmethod
    def dashboard_url_name(self) -> str: ...

    @abstractmethod
    def can_access_admin(self) -> bool: ...

    @abstractmethod
    def handled_orders(self, user): ...

    @abstractmethod
    def statistic_cards(self, agg) -> list[dict]: ...

    @abstractmethod
    def summary(self, user) -> str: ...

    # "orders" = pekerjaan peran ini berupa order barang; "bookings" = booking jasa.
    work_kind = "orders"

    def handled_bookings(self, user):
        ServiceBooking = apps.get_model("service", "ServiceBooking")
        return ServiceBooking.objects.none()


# OOP: PEWARISAN + POLIMORFISME - AdminRole, CourierRole, CashierRole, GroomerRole,
# CustomerRole mewarisi
# RoleBehavior dan menjawab method yang sama dengan cara berbeda.
class AdminRole(RoleBehavior):
    code = "ADMIN"
    label = "Admin"
    badge_class = "role-admin"
    badge_icon = "bi-shield-lock"
    summary_icon = "bi-cart-check"
    dashboard_url_name = "staff_admin_dashboard"

    def can_access_admin(self):
        return True

    def handled_orders(self, user):
        Order = apps.get_model("transaction", "Order")
        return Order.objects.filter(admin=user)

    def statistic_cards(self, agg):
        return [
            {"value": agg["total"], "label": "Order dibuat", "tone": ""},
            {
                "value": agg["confirmed"] + agg["on_delivery"],
                "label": "Masih berjalan",
                "tone": "blue",
            },
            {"value": agg["delivered"], "label": "Terkirim", "tone": "green"},
        ]

    def summary(self, user):
        return f"{user.created_count} order"


class CourierRole(RoleBehavior):
    code = "KURIR"
    label = "Kurir"
    badge_class = "role-courier"
    badge_icon = "bi-truck"
    summary_icon = "bi-box-seam"
    dashboard_url_name = "courier:dashboard"

    def can_access_admin(self):
        return False

    def handled_orders(self, user):
        Order = apps.get_model("transaction", "Order")
        return Order.objects.filter(courier=user)

    def statistic_cards(self, agg):
        return [
            {"value": agg["total"], "label": "Ditugaskan", "tone": ""},
            {"value": agg["on_delivery"], "label": "Dalam pengiriman", "tone": "blue"},
            {"value": agg["delivered"], "label": "Terkirim", "tone": "green"},
        ]

    def summary(self, user):
        return f"{user.delivered_count} terkirim"


class CashierRole(AdminRole):
    """Kasir: membuat transaksi di toko seperti admin, tapi tanpa akses menu admin."""

    code = "KASIR"
    label = "Kasir"
    badge_class = "role-cashier"
    badge_icon = "bi-cash-coin"
    summary_icon = "bi-receipt"
    dashboard_url_name = "transaction:make_transaction"

    def can_access_admin(self):
        return False


class GroomerRole(RoleBehavior):
    """Groomer: mengerjakan booking jasa layanan hewan, bukan order barang."""

    code = "GROOMER"
    label = "Groomer"
    badge_class = "role-groomer"
    badge_icon = "bi-scissors"
    summary_icon = "bi-heart-pulse"
    dashboard_url_name = "service:groomer_dashboard"
    work_kind = "bookings"

    def can_access_admin(self):
        return False

    def handled_orders(self, user):
        Order = apps.get_model("transaction", "Order")
        return Order.objects.none()

    def handled_bookings(self, user):
        ServiceBooking = apps.get_model("service", "ServiceBooking")
        return ServiceBooking.objects.filter(groomer=user)

    def statistic_cards(self, agg):
        return [
            {"value": agg["total"], "label": "Ditangani", "tone": ""},
            {"value": agg["process"], "label": "Sedang diproses", "tone": "blue"},
            {"value": agg["done"], "label": "Selesai", "tone": "green"},
        ]

    def summary(self, user):
        return f"{getattr(user, 'groomed_count', 0)} layanan selesai"


class CustomerRole(RoleBehavior):
    code = "CUSTOMER"
    label = "Customer"
    badge_class = "role-customer"
    badge_icon = "bi-person-heart"
    dashboard_url_name = "customer:home"

    def can_access_admin(self):
        return False

    def handled_orders(self, user):
        Order = apps.get_model("transaction", "Order")
        return Order.objects.none()

    def statistic_cards(self, agg):
        return []

    def summary(self, user):
        return ""


# OOP: POLIMORFISME  user.role_behavior mengembalikan objek peran yang sesuai,
# pemanggil tidak perlu if role == "ADMIN" / "KURIR" / "GROOMER".
ROLE_REGISTRY = {
    cls.code: cls()
    for cls in (AdminRole, CourierRole, CashierRole, GroomerRole, CustomerRole)
}
DEFAULT_ROLE = ROLE_REGISTRY[CustomerRole.code]


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    COURIER = "KURIR", "Kurir"
    CASHIER = "KASIR", "Kasir"
    GROOMER = "GROOMER", "Groomer"
    CUSTOMER = "CUSTOMER", "Customer"


# Peran pegawai (boleh dipilih di form "Tambah Pegawai"); CUSTOMER bukan pegawai.
STAFF_ROLES = (Role.ADMIN, Role.COURIER, Role.CASHIER, Role.GROOMER)
# Peran yang boleh membuat & mengelola transaksi kasir (POS).
POS_ROLES = (Role.ADMIN, Role.CASHIER)


def person_search(queryset, q, prefix=""):
    """Cari nama lengkap / nama pengguna / no. HP seseorang (mis. prefix="customer__").

    Mengembalikan (queryset_beranotasi, Q) supaya pemanggil bisa menambah syarat
    lain, misalnya `cond | Q(pk=...)`.
    """
    queryset = queryset.annotate(
        person_name_search=Concat(
            F(f"{prefix}first_name"), Value(" "), F(f"{prefix}last_name")
        )
    )
    cond = (
        Q(person_name_search__icontains=q)
        | Q(**{f"{prefix}username__icontains": q})
        | Q(**{f"{prefix}phone_number__icontains": q})
    )
    return queryset, cond


def _username_base(raw):
    cleaned = re.sub(r"[^\w.@+-]", "", raw or "")
    return (cleaned or "pelanggan")[:140]


# OOP: PEWARISAN  User mewarisi AbstractUser bawaan Django.
# Sejak tabel account_customer dihapus, pelanggan juga disimpan di sini
# dengan role=CUSTOMER (nama, nomor HP, dan alamat ada di User).
class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, null=False)
    phone_number = models.CharField(max_length=20)
    address = models.CharField(max_length=255, blank=True, default="")

    class Meta(AbstractUser.Meta):
        constraints = [
            # Nomor HP pelanggan tetap unik seperti di tabel Customer lama.
            models.UniqueConstraint(
                fields=["phone_number"],
                condition=models.Q(role="CUSTOMER"),
                name="unique_customer_phone",
                violation_error_message="Nomor telepon sudah dipakai pelanggan lain.",
            )
        ]

    @classmethod
    def couriers(cls):
        """Semua user ber-peran kurir (satu pintu, tidak diulang di view)."""
        return cls.objects.filter(role=Role.COURIER)

    @classmethod
    def groomers(cls):
        return cls.objects.filter(role=Role.GROOMER, is_active=True)

    @classmethod
    def customers(cls):
        return cls.objects.filter(role=Role.CUSTOMER)

    @classmethod
    def unique_username(cls, raw):
        """Nama pengguna unik dari teks bebas (mis. nomor HP): '0812', '0812-2', ..."""
        base = _username_base(raw)
        candidate, n = base, 2
        while User.objects.filter(username__iexact=candidate).exists():
            candidate = f"{base}-{n}"
            n += 1
        return candidate

    # OOP: ENKAPSULASI - info tampilan karyawan dihitung User sendiri.
    @property
    def display_name(self):
        full = f"{(self.first_name or '').strip()} {(self.last_name or '').strip()}"
        return full.strip() or self.username

    # `name` dipertahankan agar template lama ({{ order.customer.name }}) tetap jalan.
    @property
    def name(self):
        return self.display_name

    @name.setter
    def name(self, value):
        first, _, last = (value or "").strip().partition(" ")
        self.first_name = first[:150]
        self.last_name = last.strip()[:150]

    @classmethod
    def couriers(cls):
        """Semua user ber-peran kurir (satu pintu, tidak diulang di view)."""
        return cls.objects.filter(role=Role.COURIER)

    # OOP: ENKAPSULASI - info tampilan karyawan dihitung User sendiri.
    @property
    def initials(self):
        first = (self.first_name or "").strip()
        last = (self.last_name or "").strip()
        return ((first[:1] + last[:1]) or self.username[:2]).upper()

    @property
    def tone(self):
        """Warna avatar, stabil per user."""
        return (self.pk or 0) % AVATAR_TONES

    @property
    def role_behavior(self):
        return ROLE_REGISTRY.get(self.role, DEFAULT_ROLE)

    @property
    def dashboard_url_name(self):
        return self.role_behavior.dashboard_url_name

    @property
    def role_summary(self):
        return self.role_behavior.summary(self)

    @property
    def is_customer(self):
        return self.role == Role.CUSTOMER

    @property
    def whatsapp_url(self):
        number = re.sub(r"\D", "", self.phone_number or "")
        if not number:
            return ""
        number = "62" + number[1:] if number.startswith("0") else number
        return f"https://wa.me/{number}"

    @property
    def maps_url(self):
        if not self.address:
            return ""
        return f"https://www.google.com/maps/search/?api=1&query={quote(self.address)}"


class CustomerManager(UserManager):
    def get_queryset(self):
        return super().get_queryset().filter(role=Role.CUSTOMER)


# Tabel account_customer sudah dihapus. Customer sekarang hanya "proxy" di atas
# User (tanpa tabel sendiri) yang otomatis memfilter & mengisi role=CUSTOMER,
# jadi kode lama seperti Customer.objects.create(name=..., phone_number=...,
# address=...) tetap bekerja dan datanya tersimpan di account_user.
class Customer(User):
    objects = CustomerManager()

    class Meta:
        proxy = True
        verbose_name = "pelanggan"
        verbose_name_plural = "pelanggan"

    def save(self, *args, **kwargs):
        self.role = Role.CUSTOMER
        if not self.username:
            self.username = User.unique_username(self.phone_number)
        if not self.password:
            # Pelanggan yang dibuat admin belum bisa login sampai diberi kata sandi.
            self.set_unusable_password()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.phone_number})"
