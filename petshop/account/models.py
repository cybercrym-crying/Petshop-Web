from urllib.parse import quote

from django.apps import apps
from django.db import models
from django.contrib.auth.models import AbstractUser
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


# OOP: PEWARISAN + POLIMORFISME - AdminRole, CourierRole, CustomerRole mewarisi
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


class CustomerRole(RoleBehavior):
    code = ""
    label = "Pelanggan"
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


# OOP: POLIMORFISME - user.role_behavior mengembalikan objek peran yang sesuai,
# pemanggil tidak perlu if role == "ADMIN" / "KURIR".
ROLE_REGISTRY = {cls.code: cls() for cls in (AdminRole, CourierRole)}
DEFAULT_ROLE = CustomerRole()


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    COURIER = "KURIR", "Kurir"


# OOP: PEWARISAN - User mewarisi AbstractUser bawaan Django.
class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, null=False)
    phone_number = models.CharField(max_length=20)

    @classmethod
    def couriers(cls):
        """Semua user ber-peran kurir (satu pintu, tidak diulang di view)."""
        return cls.objects.filter(role=Role.COURIER)

    # OOP: ENKAPSULASI - info tampilan karyawan dihitung User sendiri.
    @property
    def display_name(self):
        full = f"{(self.first_name or '').strip()} {(self.last_name or '').strip()}"
        return full.strip() or self.username

    @property
    def initials(self):
        first = (self.first_name or "").strip()
        last = (self.last_name or "").strip()
        return ((first[:1] + last[:1]) or self.username[:2]).upper()

    @property
    def tone(self):
        """Warna avatar, stabil per user."""
        return self.pk % AVATAR_TONES

    @property
    def role_behavior(self):
        return ROLE_REGISTRY.get(self.role, DEFAULT_ROLE)

    @property
    def dashboard_url_name(self):
        return self.role_behavior.dashboard_url_name

    @property
    def role_summary(self):
        return self.role_behavior.summary(self)


class Customer(models.Model):
    name = models.CharField(max_length=255, null=False, blank=False)
    phone_number = models.CharField(max_length=20, null=False, blank=False, unique=True)
    address = models.CharField(max_length=255, null=False, blank=False)

    @property
    def whatsapp_url(self):
        number = self.phone_number
        number = "62" + number[1:] if number.startswith("0") else number
        return f"https://wa.me/{number}"

    @property
    def maps_url(self):
        return f"https://www.google.com/maps/search/?api=1&query={quote(self.address)}"

    def __str__(self):
        return f"{self.name} ({self.phone_number})"
