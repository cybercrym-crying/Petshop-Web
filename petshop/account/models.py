from django.core.exceptions import ObjectDoesNotExist
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
import re
from urllib.parse import quote

from django.apps import apps
from django.db import models
from django.utils import timezone
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


class SuperAdminRole(AdminRole):
    """Super Admin: semua hak Admin + mengelola akun Admin/Super Admin."""

    code = "SUPERADMIN"
    label = "Super Admin"
    badge_class = "role-admin"
    badge_icon = "bi-stars"


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
    dashboard_url_name = "transaction:cashier_home"

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
    dashboard_url_name = "customer:dashboard"

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
    for cls in (
        SuperAdminRole,
        AdminRole,
        CourierRole,
        CashierRole,
        GroomerRole,
        CustomerRole,
    )
}
DEFAULT_ROLE = ROLE_REGISTRY[CustomerRole.code]


class Role(models.TextChoices):
    SUPERADMIN = "SUPERADMIN", _("Super Admin")
    ADMIN = "ADMIN", _("Admin")
    COURIER = "KURIR", _("Kurir")
    CASHIER = "KASIR", _("Kasir")
    GROOMER = "GROOMER", _("Groomer")
    CUSTOMER = "CUSTOMER", _("Customer")


# Peran pegawai (boleh dipilih di form "Tambah Pegawai"); CUSTOMER bukan pegawai.
STAFF_ROLES = (Role.SUPERADMIN, Role.ADMIN, Role.COURIER, Role.CASHIER, Role.GROOMER)
# Peran tingkat admin. Hanya Super Admin yang boleh membuat/mengubah akun ini.
ADMIN_ROLES = (Role.SUPERADMIN, Role.ADMIN)
# Peran yang boleh didaftarkan sendiri lewat situs (aktif setelah disetujui admin).
# Staf lain (kasir, groomer) hanya dibuat Admin/Super Admin lewat Kelola Akun.
SELF_REGISTER_ROLES = (Role.COURIER,)


class Approval(models.TextChoices):
    APPROVED = "DISETUJUI", _("Disetujui")
    PENDING = "MENUNGGU", _("Menunggu persetujuan")
    REJECTED = "DITOLAK", _("Ditolak")

# Peran yang boleh membuat & mengelola transaksi kasir (POS).
POS_ROLES = (Role.SUPERADMIN, Role.ADMIN, Role.CASHIER)
# Nama pengguna akun sistem untuk pembeli kasir tanpa akun.
WALK_IN_USERNAME = "pelanggan_umum"


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
    # Titik rumah dari peta (opsional): dipakai untuk ongkir & rute kurir.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # Staf yang mendaftar sendiri baru aktif setelah disetujui admin.
    approval = models.CharField(
        "Status persetujuan",
        max_length=12,
        choices=Approval.choices,
        default=Approval.APPROVED,
    )
    approved_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    # Akun sistem "Pelanggan umum" untuk pembeli di kasir tanpa akun (tidak bisa login,
    # tidak tampil di daftar pelanggan). Nama/HP pembeli disimpan di order.
    is_walk_in = models.BooleanField(default=False, editable=False)

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

    @cached_property  # dipakai berulang di daftar kurir tiap pesanan: cukup satu query per kurir
    def on_pet_trip(self):
        """Kurir sedang antar-jemput hewan: belum boleh diberi paket (lihat ServiceBooking.active_trip)."""
        from service.models import ServiceBooking

        return ServiceBooking.active_trip(self) is not None

    @classmethod
    def pet_couriers(cls):
        """Kurir aktif yang membawa kandang/boks hewan (boleh antar-jemput hewan grooming)."""
        return cls.objects.filter(
            role=Role.COURIER, is_active=True, courier_profile__can_carry_pets=True
        )

    @classmethod
    def customers(cls):
        return cls.objects.filter(role=Role.CUSTOMER, is_walk_in=False)

    @classmethod
    def walk_in(cls):
        """Akun 'Pelanggan umum' (dibuat migrasi; dibuat ulang bila terhapus)."""
        user = cls.objects.filter(is_walk_in=True).first()
        if user is None:
            user = cls(
                username=WALK_IN_USERNAME, first_name="Pelanggan", last_name="umum",
                role=Role.CUSTOMER, phone_number=WALK_IN_USERNAME, is_active=False,
                is_walk_in=True,
            )
            user.set_unusable_password()
            user.save()
        return user

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
    def photo_url(self):
        """Foto profil kurir (kosong kalau belum diunggah atau bukan kurir)."""
        if self.role != Role.COURIER:
            return ""
        try:
            photo = self.courier_profile.photo
        except ObjectDoesNotExist:
            return ""
        return photo.url if photo else ""

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
    def is_admin_level(self):
        return self.role in ADMIN_ROLES

    @property
    def is_superadmin(self):
        return self.role == Role.SUPERADMIN

    def can_manage(self, other_role):
        """Admin mengelola semua akun staf kecuali akun tingkat admin."""
        if self.is_superadmin:
            return True
        return self.role == Role.ADMIN and other_role not in ADMIN_ROLES

    def decide_registration(self, staff, approve):
        """Admin menyetujui/menolak staf yang mendaftar sendiri."""
        if staff.approval != Approval.PENDING:
            return False
        staff.approval = Approval.APPROVED if approve else Approval.REJECTED
        staff.is_active = approve
        staff.approved_by = self
        staff.approved_at = timezone.now()
        staff.save(update_fields=["approval", "is_active", "approved_by", "approved_at"])
        return True

    @property
    def whatsapp_url(self):
        number = re.sub(r"\D", "", self.phone_number or "")
        if not number:
            return ""
        number = "62" + number[1:] if number.startswith("0") else number
        return f"https://wa.me/{number}"

    @property
    def has_pin(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def maps_url(self):
        if self.has_pin:
            return f"https://www.google.com/maps/search/?api=1&query={self.latitude},{self.longitude}"
        if not self.address:
            return ""
        return f"https://www.google.com/maps/search/?api=1&query={quote(self.address)}"


class CustomerManager(UserManager):
    def get_queryset(self):
        return super().get_queryset().filter(role=Role.CUSTOMER, is_walk_in=False)


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
