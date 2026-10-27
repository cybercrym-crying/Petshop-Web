"""Laporan kasir: penjualan per metode bayar, per kasir, online vs offline, retur, dan shift."""

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from .models import (
    COUNTER_PAYMENT_METHODS,
    CashierShift,
    Order,
    OrderChannel,
    OrderPayment,
    OrderServiceLine,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ReturnRequest,
    ReturnStatus,
)


def _paid(qs):
    return qs.filter(payment_status=PaymentStatus.PAID).exclude(order_status=OrderStatus.CANCELLED)


def cashier_report(period):
    in_range = Order.objects.filter(date__gte=period.start, date__lte=period.end)
    store = _paid(in_range.filter(channel=OrderChannel.STORE))
    online = _paid(in_range.filter(channel=OrderChannel.ONLINE))

    methods = {m: 0 for m in (*COUNTER_PAYMENT_METHODS,)}
    for row in OrderPayment.objects.filter(order__in=store).values("method").annotate(t=Sum("amount")):
        methods[row["method"]] = methods.get(row["method"], 0) + (row["t"] or 0)
    # Transaksi toko lama (sebelum ada baris pembayaran), COD dari kasir, & pesanan online: pakai metode order.
    legacy = store.filter(payments__isnull=True)
    for qs in (legacy, online):
        for row in qs.values("payment_method").annotate(t=Sum("total_payment")):
            methods[row["payment_method"]] = methods.get(row["payment_method"], 0) + (row["t"] or 0)
    by_method = [
        {"code": code, "label": PaymentMethod(code).label, "total": total}
        for code, total in methods.items() if code != PaymentMethod.MIXED
    ]

    channel = {
        "offline": store.aggregate(n=Count("pk"), total=Coalesce(Sum("total_payment"), 0)),
        "online": online.aggregate(n=Count("pk"), total=Coalesce(Sum("total_payment"), 0)),
    }
    by_cashier = list(
        store.values("admin__username", "admin__first_name", "admin__last_name")
        .annotate(
            n=Count("pk"),
            total=Coalesce(Sum("total_payment"), 0),
            discount=Coalesce(Sum("discount"), 0),
            take_away=Count("pk", filter=Q(fulfillment="BAWA")),
        )
        .order_by("-total")
    )
    for row in by_cashier:
        name = f"{row['admin__first_name'] or ''} {row['admin__last_name'] or ''}".strip()
        row["name"] = name or row["admin__username"] or "-"
    voided = Order.objects.filter(voided_at__gte=period.start, voided_at__lte=period.end)
    returns = ReturnRequest.objects.filter(
        status=ReturnStatus.APPROVED, decided_at__gte=period.start, decided_at__lte=period.end
    ).aggregate(n=Count("pk"), total=Coalesce(Sum("refund_amount"), 0))
    # Layanan grooming: dibayar di kasir atau transfer setelah booking dikonfirmasi.
    services = OrderServiceLine.objects.filter(order__in=_paid(in_range)).aggregate(
        n=Count("pk"), total=Coalesce(Sum("amount"), 0)
    )
    shifts = list(
        CashierShift.objects.filter(opened_at__gte=period.start, opened_at__lte=period.end)
        .select_related("cashier")[:60]
    )
    # Angka turunan untuk tampilan ringkas: total uang masuk, porsi tiap metode/kasir, rata-rata.
    total_in = channel["offline"]["total"] + channel["online"]["total"]
    for row in by_method:
        row["pct"] = round(row["total"] * 100 / total_in) if total_in else 0
    best = max((c["total"] for c in by_cashier), default=0)
    for row in by_cashier:
        row["pct"] = round(row["total"] * 100 / best) if best else 0
    offline_n = channel["offline"]["n"]
    return {
        "total_in": total_in,
        "avg_offline": channel["offline"]["total"] // offline_n if offline_n else 0,
        "daily": daily_sales(period),
        "by_method": by_method,
        "channel": channel,
        "by_cashier": by_cashier,
        "voided": voided.aggregate(n=Count("pk"), total=Coalesce(Sum("total_payment"), 0)),
        "returns": returns,
        "services": services,
        "discount": store.aggregate(t=Coalesce(Sum("discount"), 0))["t"],
        "shifts": shifts,
        "pending_returns": ReturnRequest.objects.filter(status=ReturnStatus.PENDING).count(),
    }


def daily_sales(period):
    """Uang masuk per hari (kasir + online, sudah lunas), termasuk hari tanpa penjualan."""
    rows = (
        _paid(Order.objects.filter(date__gte=period.start, date__lte=period.end))
        .annotate(day=TruncDate("date", tzinfo=timezone.get_current_timezone()))
        .values("day", "channel")
        .annotate(total=Coalesce(Sum("total_payment"), 0), n=Count("pk"))
    )
    first = timezone.localdate(period.start)
    days = [first + timedelta(days=i) for i in range(period.days)]
    totals = {d: {"day": d, "offline": 0, "online": 0, "n": 0} for d in days}
    for row in rows:
        slot = totals.get(row["day"])
        if slot is None:
            continue
        key = "offline" if row["channel"] == OrderChannel.STORE else "online"
        slot[key] += row["total"]
        slot["n"] += row["n"]
    series = [totals[d] for d in days]
    peak = max((d["offline"] + d["online"] for d in series), default=0)
    step = 1 if period.days <= 7 else (5 if period.days <= 31 else 15)
    for i, d in enumerate(series):
        d["label"] = i % step == 0 or i == len(series) - 1
        d["total"] = d["offline"] + d["online"]
        d["pct"] = round(d["total"] * 100 / peak) if peak else 0
        d["is_peak"] = peak > 0 and d["total"] == peak
    return {"days": series, "peak": peak}


def counter_sales(period):
    """Transaksi kasir (ber-struk) pada rentang, untuk tabel & CSV."""
    return (
        Order.objects.filter(date__gte=period.start, date__lte=period.end, receipt_no__isnull=False)
        .select_related("admin", "customer")
        .prefetch_related("payments")
        .order_by("-date", "-pk")
    )
