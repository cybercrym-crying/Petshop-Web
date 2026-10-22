from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from account.decorators import roleRequired
from account.models import Role, person_search
from common.exceptions import PetshopError
from .forms import DeliveryProofForm
from .models import CourierLocation
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
        orders, filters = person_search(orders, q, prefix="customer__")
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
            "has_active_delivery": Order.objects.filter(
                courier=request.user, order_status=OrderStatus.ON_DELIVERY
            ).exists(),
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
    return render(
        request,
        "courier/order_detail.html",
        {"order": order, "proof_form": DeliveryProofForm()},
    )


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
            # Selesai = wajib foto bukti, supaya admin & pelanggan tahu barang sampai.
            form = DeliveryProofForm(request.POST, request.FILES)
            if not form.is_valid():
                for errors in form.errors.values():
                    for error in errors:
                        messages.error(request, error)
                return redirect("courier:order_detail", pk=order.pk)
            order.mark_delivered(
                photo=form.cleaned_data["photo"], note=form.cleaned_data["note"]
            )
            messages.success(
                request, f"Order #{order.pk} berhasil dikirim, foto bukti tersimpan."
            )
        else:
            messages.error(request, "Aksi tidak tersedia.")
    except PetshopError as error:
        messages.error(request, str(error))

    status = _board_status(request.POST.get("status"))
    return redirect(f"{reverse('courier:dashboard')}?status={status}")


MIN_PING_INTERVAL = timedelta(seconds=5)  # HP mengirim tiap ±15 dtk; ini sekadar rem


def _coordinate(raw, limit):
    try:
        value = Decimal(str(raw)).quantize(Decimal("0.000001"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return value if -limit <= value <= limit else None


@roleRequired(Role.COURIER)
@require_POST
def share_location(request):
    """Terima lokasi GPS dari HP kurir (navigator.geolocation di browser).

    Lokasi hanya disimpan selama kurir sedang mengantar paket, jadi kurir
    tidak terlacak di luar jam pengiriman.
    """
    active = Order.objects.filter(
        courier=request.user, order_status=OrderStatus.ON_DELIVERY
    ).count()
    if not active:
        return JsonResponse(
            {"ok": False, "reason": "no_active", "message": "Tidak ada paket yang sedang diantar."},
            status=409,
        )

    lat = _coordinate(request.POST.get("lat"), 90)
    lng = _coordinate(request.POST.get("lng"), 180)
    if lat is None or lng is None:
        return JsonResponse({"ok": False, "reason": "invalid", "message": "Koordinat tidak valid."}, status=400)
    try:
        accuracy = max(0, min(int(float(request.POST.get("accuracy") or 0)), 100000)) or None
    except ValueError:
        accuracy = None

    now = timezone.now()
    last = CourierLocation.objects.filter(courier=request.user).order_by("-recorded_at").first()
    if last and now - last.recorded_at < MIN_PING_INTERVAL:
        return JsonResponse({"ok": True, "saved": False, "active_orders": active})

    CourierLocation.objects.create(
        courier=request.user,
        latitude=lat,
        longitude=lng,
        accuracy=accuracy,
        recorded_at=now,
    )
    return JsonResponse(
        {"ok": True, "saved": True, "active_orders": active, "at": now.isoformat()}
    )
