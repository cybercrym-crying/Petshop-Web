"""Laporan kasir: penjualan per metode bayar, per kasir, online vs offline, retur, dan shift."""

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

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
    # Transaksi toko lama (sebelum ada baris pembayaran) & pesanan online: pakai metode order.
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
    return {
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


def counter_sales(period):
    """Transaksi kasir (ber-struk) pada rentang, untuk tabel & CSV."""
    return (
        Order.objects.filter(date__gte=period.start, date__lte=period.end, receipt_no__isnull=False)
        .select_related("admin", "customer")
        .prefetch_related("payments")
        .order_by("-date", "-pk")
    )
