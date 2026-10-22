from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from account.decorators import roleRequired
from account.models import Role
from common.exceptions import PetshopError
from transaction.models import Order, OrderStatus, PaymentMethod, PaymentStatus

BOARD_DONE_LIMIT = 15
BOARD_STATUSES = ("pending", "on_delivery", "done")
BOARD_META = {
    "pending": {
        "title": "Menunggu Dikirim",
        "icon": "bi-clock-history",
        "action": "on_delivery",
        "empty": "Tidak ada pesanan yang menunggu dikirim.",
    },
    "on_delivery": {
        "title": "Sedang Dikirim",
        "icon": "bi-truck",
        "action": "delivered",
        "empty": "Belum ada pesanan yang sedang dikirim.",
    },
    "done": {
        "title": "Riwayat Pengiriman",
        "icon": "bi-check2-circle",
        "action": "",
        "empty": "Belum ada pengiriman yang selesai.",
    },
}


def _board_status(raw):
    return raw if raw in BOARD_STATUSES else "pending"


@roleRequired(Role.COURIER)
def dashboard(request):
    q = (request.GET.get("q") or "").strip()
    current = _board_status(request.GET.get("status"))
    orders = (
        Order.objects.filter(courier=request.user)
        .select_related("customer", "admin", "courier")
        .prefetch_related("details__product")
        .order_by("-date")
    )

    if q:
        filters = Q(customer__name__icontains=q)
        if q.isdigit():
            filters |= Q(pk=int(q))
        orders = orders.filter(filters)

    # Siap-kirim ditentukan Order.is_ready_to_ship (lewat Payment), bukan string
    # "cod"/"paid" di view. Disaring di Python agar aturan tetap satu tempat.
    pending_ids = [
        o.pk for o in orders.filter(order_status=OrderStatus.CONFIRMED) if o.is_ready_to_ship
    ]
    pending_orders = orders.filter(pk__in=pending_ids).order_by("date")

    on_delivery_orders = orders.filter(order_status=OrderStatus.ON_DELIVERY).order_by(
        "date"
    )
    delivered_orders = orders.filter(order_status=OrderStatus.DELIVERED)

    return render(
        request,
        "courier/dashboard.html",
        {
            "q": q,
            "current": current,
            "meta": BOARD_META[current],
            "current_orders": {
                "pending": pending_orders,
                "on_delivery": on_delivery_orders,
                "done": delivered_orders[:BOARD_DONE_LIMIT],
            }[current],
            "total_pending": pending_orders.count(),
            "total_on_delivery": on_delivery_orders.count(),
            "total_delivered": delivered_orders.count(),
            "done_limit": BOARD_DONE_LIMIT,
        },
    )


@roleRequired(Role.COURIER)
def history(request):
    history_orders = (
        Order.objects.filter(courier=request.user)
        .select_related("customer", "admin")
        .prefetch_related("details__product")
        .order_by("-date")
    )

    return render(
        request,
        "courier/history.html",
        {"history_orders": history_orders},
    )


@roleRequired(Role.COURIER)
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer", "admin", "courier").prefetch_related(
            "details__product"
        ),
        pk=pk,
        courier=request.user,
    )
    return render(request, "courier/order_detail.html", {"order": order})


@roleRequired(Role.COURIER)
@transaction.atomic
def update_status(request, pk):
    if request.method != "POST":
        return redirect("courier:dashboard")

    order = get_object_or_404(
        Order.objects.select_for_update(), pk=pk, courier=request.user
    )
    action = request.POST.get("action")

    try:
        if action == "on_delivery":
            order.mark_on_delivery(request.user)
            messages.success(request, f"Order #{order.pk} sedang dikirim.")
        elif action == "delivered":
            order.mark_delivered()
            messages.success(request, f"Order #{order.pk} berhasil dikirim.")
        else:
            messages.error(request, "Aksi tidak tersedia.")
    except PetshopError as error:
        messages.error(request, str(error))

    status = _board_status(request.POST.get("status"))
    return redirect(f"{reverse('courier:dashboard')}?status={status}")
