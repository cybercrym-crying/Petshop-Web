"""Angka-angka dasbor admin. Semua dihitung dari database, tanpa data contoh.

Definisi metrik (juga ditampilkan sebagai keterangan di dasbor):

- Penjualan lunas: jumlah total_payment order berstatus bayar LUNAS dan tidak
  dibatalkan, berdasarkan tanggal order. Order tunai baru lunas saat diterima.
- Belum dibayar: total order yang masih berjalan (belum dibatalkan) tapi
  pembayarannya masih MENUNGGU.
- Pesanan: jumlah order yang tidak dibatalkan pada rentang tanggal.
- Layanan selesai: jumlah & nilai booking jasa berstatus SELESAI (harga yang
  disalin saat booking), berdasarkan waktu selesai.
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from django.utils.translation import gettext_lazy

from account.models import User
from product.models import LOW_STOCK_THRESHOLD, Product
from service.models import OPEN_BOOKING_STATUSES, WORK_DONE_STATUSES, ServiceBooking
from transaction.models import (
    Order,
    OrderDetail,
    OrderStatus,
    PaymentStatus,
)

RANGE_CHOICES = (1, 7, 30, 90)
DEFAULT_RANGE = 7


def parse_range(raw):
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RANGE
    return days if days in RANGE_CHOICES else DEFAULT_RANGE


@dataclass
class Period:
    days: int
    start: object  # datetime aware, awal hari pertama (waktu lokal)
    end: object  # datetime aware, sekarang

    @classmethod
    def last_days(cls, days, now=None):
        now = now or timezone.now()
        first_day = timezone.localdate(now) - timedelta(days=days - 1)
        start = timezone.make_aware(datetime.combine(first_day, time.min))
        return cls(days=days, start=start, end=now)

    def previous(self):
        """Rentang sebelumnya dengan panjang & jam yang sama (pembanding "dari kemarin" / "dari 7 hari sebelumnya")."""
        shift = timedelta(days=self.days)
        return Period(days=self.days, start=self.start - shift, end=self.end - shift)


def orders_in(period):
    return Order.objects.filter(date__gte=period.start, date__lte=period.end)


def paid_orders(queryset):
    return queryset.filter(payment_status=PaymentStatus.PAID).exclude(
        order_status=OrderStatus.CANCELLED
    )


def sales_trend(period):
    """[(tanggal, total_lunas, jumlah_order)] untuk setiap hari, termasuk hari kosong."""
    rows = (
        paid_orders(orders_in(period))
        .annotate(day=TruncDate("date"))
        .values("day")
        .annotate(
            total=Sum("total_payment"), n=Count("pk"),
            store=Coalesce(Sum("total_payment", filter=Q(channel="TOKO")), 0),
            online=Coalesce(Sum("total_payment", filter=Q(channel="ONLINE")), 0),
        )
    )
    by_day = {row["day"]: row for row in rows}
    first = timezone.localdate(period.start)
    trend = []
    for offset in range(period.days):
        day = first + timedelta(days=offset)
        row = by_day.get(day, {})
        trend.append({
            "day": day, "total": row.get("total") or 0, "n": row.get("n") or 0,
            "store": row.get("store") or 0, "online": row.get("online") or 0,
        })
    peak = max((point["total"] for point in trend), default=0)
    for point in trend:
        point["pct"] = round(point["total"] * 100 / peak) if peak else 0
        point["store_pct"] = round(point["store"] * 100 / peak) if peak else 0
        point["online_pct"] = round(point["online"] * 100 / peak) if peak else 0
    return trend


def top_products(period, limit=5):
    return list(
        OrderDetail.objects.filter(
            transaction__date__gte=period.start, transaction__date__lte=period.end
        )
        .exclude(transaction__order_status=OrderStatus.CANCELLED)
        .values("product_id", "product__name")
        .annotate(qty=Sum("quantity"), revenue=Sum("subtotal"))
        .order_by("-qty", "product__name")[:limit]
    )


def summary(period):
    in_range = orders_in(period)
    sales = paid_orders(in_range).aggregate(
        total=Coalesce(Sum("total_payment"), 0), n=Count("pk"),
        offline=Coalesce(Sum("total_payment", filter=Q(channel="TOKO")), 0),
        online=Coalesce(Sum("total_payment", filter=Q(channel="ONLINE")), 0),
    )
    orders = in_range.exclude(order_status=OrderStatus.CANCELLED).aggregate(
        n=Count("pk"),
        online=Count("pk", filter=Q(channel="ONLINE")),
    )
    open_orders = Order.objects.filter(
        order_status__in=[
            OrderStatus.PENDING,
            OrderStatus.CONFIRMED,
            OrderStatus.ON_DELIVERY,
        ]
    )
    work = open_orders.aggregate(
        pending=Count("pk", filter=Q(order_status=OrderStatus.PENDING)),
        to_ship=Count(
            "pk",
            filter=Q(order_status=OrderStatus.CONFIRMED, courier__isnull=True),
        ),
        on_delivery=Count("pk", filter=Q(order_status=OrderStatus.ON_DELIVERY)),
        unpaid_n=Count("pk", filter=Q(payment_status=PaymentStatus.PENDING)),
        unpaid_total=Coalesce(
            Sum("total_payment", filter=Q(payment_status=PaymentStatus.PENDING)), 0
        ),
    )
    stock = Product.objects.filter(is_active=True).aggregate(
        active=Count("pk", filter=Q(selling_price__isnull=False)),
        low=Count("pk", filter=Q(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD)),
        empty=Count("pk", filter=Q(stock=0)),
        no_price=Count("pk", filter=Q(selling_price__isnull=True)),
    )
    customers = User.customers().aggregate(
        total=Count("pk"),
        new=Count("pk", filter=Q(date_joined__gte=period.start)),
    )
    services = ServiceBooking.objects.filter(
        status__in=WORK_DONE_STATUSES,
        finished_at__gte=period.start,
        finished_at__lte=period.end,
    ).aggregate(n=Count("pk"), total=Coalesce(Sum("price"), 0))
    return {
        "sales": sales,
        "orders": orders,
        "work": work,
        "stock": stock,
        "customers": customers,
        "services": services,
        "avg_order": sales["total"] // sales["n"] if sales["n"] else 0,
    }


def upcoming_bookings(limit=5):
    return list(
        ServiceBooking.objects.filter(
            status__in=OPEN_BOOKING_STATUSES,
            schedule__gte=timezone.now() - timedelta(hours=2),
        )
        .select_related("customer", "service", "groomer")
        .order_by("schedule")[:limit]
    )


def low_stock_products(limit=6):
    return list(
        Product.objects.filter(is_active=True, stock__lte=LOW_STOCK_THRESHOLD)
        .select_related("category")
        .order_by("stock", "name")[:limit]
    )


def recent_orders(limit=6):
    return list(
        Order.objects.select_related("customer").order_by("-date", "-pk")[:limit]
    )


# ---------------------------------------------------------------- tampilan dasbor baru


def change(current, previous):
    """Perubahan terhadap periode sebelumnya: {'dir': up|down|flat, 'pct': int|None, 'diff': int}."""
    diff = (current or 0) - (previous or 0)
    pct = round(diff * 100 / previous) if previous else None
    return {"dir": "up" if diff > 0 else "down" if diff < 0 else "flat", "pct": abs(pct) if pct is not None else None,
            "diff": abs(diff)}


def comparison(period):
    """Angka periode ini vs periode sebelumnya untuk kartu ringkasan."""
    now, before = summary(period), summary(period.previous())
    return {
        "sales": change(now["sales"]["total"], before["sales"]["total"]),
        "orders": change(now["orders"]["n"], before["orders"]["n"]),
        "services": change(now["services"]["n"], before["services"]["n"]),
    }


def _task(n, label, url, cta, tone="warn", hint="", group="order"):
    return {"n": n, "label": label, "url": url, "cta": cta, "tone": tone, "hint": hint, "group": group}


# Urutan kelompok tugas di beranda admin.
TASK_GROUPS = (
    ("pay", gettext_lazy("Pembayaran")),
    ("order", gettext_lazy("Pesanan")),
    ("stock", gettext_lazy("Stok & produk")),
    ("service", gettext_lazy("Layanan & staf")),
)


def group_tasks(tasks):
    """Kelompokkan hasil staff_tasks per jenis pekerjaan; kelompok kosong dibuang."""
    return [
        {"key": key, "label": label, "items": items}
        for key, label in TASK_GROUPS
        if (items := [t for t in tasks if t["group"] == key])
    ]


def staff_tasks(user):
    """Pekerjaan yang menunggu, urut dari paling mendesak; hanya yang jumlahnya > 0."""
    from django.urls import reverse
    from django.utils.translation import gettext as _

    from account.models import ADMIN_ROLES, Approval
    from courier.models import CashRemittance, RemittanceStatus
    from service.models import BookingStatus
    from store.models import Complaint, ComplaintStatus
    from transaction.models import ReturnRequest, ReturnStatus

    admin = user.role in ADMIN_ROLES
    today = timezone.localdate()
    proof = (
        Order.objects.filter(payment_status=PaymentStatus.PENDING).exclude(order_status=OrderStatus.CANCELLED)
        .exclude(payment_proof="").exclude(payment_proof__isnull=True).count()
    )
    pending = Order.objects.filter(order_status=OrderStatus.PENDING).count()
    to_pack = Order.objects.filter(
        order_status=OrderStatus.CONFIRMED, packing_seq__isnull=False, packed_at__isnull=True
    ).count()
    remit = CashRemittance.objects.filter(status=RemittanceStatus.SUBMITTED)
    not_in = ServiceBooking.objects.filter(
        schedule__date=today, status__in=[BookingStatus.SCHEDULED, BookingStatus.PENDING]
    )
    returns = ReturnRequest.objects.filter(status=ReturnStatus.PENDING).count()
    complaints = Complaint.objects.filter(status=ComplaintStatus.OPEN).count()
    manage = reverse("transaction:manage_transaction")
    tasks = [
        _task(proof, _("Bukti transfer menunggu dicek"), manage + "?payment=proof", _("Cek"),
              hint=_("Cocokkan dengan mutasi rekening"), group="pay"),
        _task(pending, _("Pesanan online menunggu konfirmasi"), manage, _("Konfirmasi")),
        _task(to_pack, _("Pesanan perlu dikemas"), reverse("transaction:packing_queue"), _("Kemas"), "run",
              _("Cetak label QR lalu tempel")),
        _task(remit.count(), _("Setoran COD dari kurir"), reverse("transaction:remittances"), _("Terima"),
              hint=_("Hitung uangnya sebelum diterima"), group="pay"),
        _task(not_in.count(), _("Booking hari ini belum check-in"), reverse("service:check_in"), _("Check-in"), "run", group="service"),
        _task(returns, _("Retur menunggu persetujuan"), reverse("transaction:returns"),
              _("Putuskan") if admin else _("Lihat"),
              hint="" if admin else _("Diputuskan admin")),
        _task(complaints, _("Komplain baru"), reverse("store:staff_complaints"), _("Balas"), "bad"),
    ]
    if admin:
        stock = Product.objects.filter(is_active=True).aggregate(
            empty=Count("pk", filter=Q(stock=0)),
            low=Count("pk", filter=Q(stock__gt=0, stock__lte=LOW_STOCK_THRESHOLD)),
            no_price=Count("pk", filter=Q(selling_price__isnull=True)),
        )
        products = reverse("product:product_list")
        tasks[2:2] = [_task(stock["empty"], _("Produk aktif stoknya habis"), products + "?filter=empty", _("Isi stok"), "bad",
                             group="stock")]
        tasks += [
            _task(User.objects.filter(approval=Approval.PENDING).count(), _("Pendaftar staf menunggu persetujuan"),
                  reverse("manage_account") + "?tab=approval", _("Tinjau"), group="service"),
            _task(stock["low"], _("Produk stok menipis"), products + "?filter=low", _("Lihat"), "warn",
                  _("Sisa %(n)s atau kurang") % {"n": LOW_STOCK_THRESHOLD}, group="stock"),
            _task(stock["no_price"], _("Produk aktif belum punya harga jual"), products + "?filter=noprice", _("Atur harga"), group="stock"),
        ]
    return [t for t in tasks if t["n"]]


def bookings_today():
    from service.models import BookingStatus

    return list(
        ServiceBooking.objects.filter(schedule__date=timezone.localdate())
        .exclude(status__in=[BookingStatus.CANCELLED, BookingStatus.NO_SHOW])
        .select_related("customer", "service", "groomer")
        .order_by("schedule")[:8]
    )


BOOKING_TONES = {
    "PENDING": "warn", "TERJADWAL": "mute", "DIJEMPUT": "run", "ANTRE": "warn", "PROSES": "run",
    "SIAP": "ok", "DIANTAR": "run", "SELESAI": "ok",
}
ORDER_TONES = {
    "MENUNGGU": "warn", "DIKONFIRMASI": "run", "DALAM_PENGIRIMAN": "run", "TERKIRIM": "ok", "DIBATALKAN": "bad",
}


def cashier_now():
    """Shift kasir yang sedang buka (dengan ringkasannya) dan shift terakhir yang ditutup."""
    from transaction.models import CashierShift, ShiftStatus

    open_shifts = []
    for shift in CashierShift.objects.filter(status=ShiftStatus.OPEN).select_related("cashier"):
        shift.info = shift.summary()
        open_shifts.append(shift)
    last_closed = CashierShift.objects.filter(status=ShiftStatus.CLOSED).select_related("cashier").first()
    return {"open": open_shifts, "last_closed": last_closed}


def couriers_now():
    """Status tiap kurir aktif: antar-jemput hewan, membawa paket, atau siap di toko."""
    from django.db.models import Count, Q
    from django.utils.translation import gettext as _

    from account.models import User
    from service.models import BookingStatus, ServiceBooking
    from transaction.models import OrderStatus

    couriers = (
        User.couriers()
        .filter(is_active=True)
        .annotate(packages=Count("orders_as_courier", filter=Q(orders_as_courier__order_status=OrderStatus.ON_DELIVERY)))
        .order_by("first_name", "username")
    )
    trips = {
        b.pet_courier_id: b
        for b in ServiceBooking.objects.filter(
            pet_courier__in=couriers, status__in=[BookingStatus.PICKUP, BookingStatus.RETURNING]
        ).order_by("-transport_started_at")
    }
    rows = []
    for c in couriers:
        trip = trips.get(c.pk)
        if trip:
            rows.append({"user": c, "tone": "run", "status": _("Antar-jemput hewan"),
                         "task": _("%(pet)s, booking #%(pk)s") % {"pet": trip.pet_name, "pk": trip.pk}})
        elif c.packages:
            rows.append({"user": c, "tone": "warn", "status": _("Antar paket"),
                         "task": _("%(n)s paket di jalan") % {"n": c.packages}})
        else:
            rows.append({"user": c, "tone": "ok", "status": _("Siap"), "task": _("Tidak membawa paket")})
    return rows
