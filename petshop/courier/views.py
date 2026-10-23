from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.utils.translation import gettext as _
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
from common.photos import CameraPhotoForm
from service.models import ServiceBooking
from store.models import Notification, StoreSettings
from transaction.models import Order, OrderStatus, PaymentMethod, PaymentStatus, normalize_tracking_number
from transaction.notify import order_event

from . import routing
from .forms import ProblemForm
from .models import CashRemittance, CourierLocation, RemittanceStatus

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
def packages(request):
    """Daftar paket per status (tanpa tombol aksi; ambil & serah wajib lewat scan QR)."""
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
        "courier/packages.html",
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
        {"order": order, "history": order_history(order)},
    )


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

    GPS wajib hidup selama kurir memakai aplikasi (dipakai untuk mengunci fitur
    saat GPS mati dan menghitung rute). Pelanggan hanya bisa melihat jejak
    kurir selama paketnya sedang diantar (lihat CourierLocation.trail_for).
    """
    active = Order.objects.filter(
        courier=request.user, order_status=OrderStatus.ON_DELIVERY
    ).count()

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


def order_history(order):
    from store.models import ActivityLog

    return ActivityLog.for_object(order)


GPS_REQUIRED = "GPS Anda belum aktif. Nyalakan Lokasi/GPS di HP lalu tunggu sampai layar tidak terkunci."


def _require_gps(request):
    if CourierLocation.is_fresh(request.user):
        return True
    messages.error(request, GPS_REQUIRED)
    return False


@roleRequired(Role.COURIER)
def dashboard(request):
    """Halaman utama kurir: peta rute realtime dengan tujuan berikutnya."""
    start, stops = routing.route_for(request.user)
    store = StoreSettings.current()
    ready = Order.objects.filter(
        Q(courier=request.user) | Q(courier__isnull=True),
        order_status=OrderStatus.CONFIRMED,
        packing_seq__isnull=False,
    )
    cash = Order.cash_on_hand(request.user)
    next_stop = stops[0] if stops else None
    if next_stop:
        next_stop.cod_due = next_stop.payment_method == PaymentMethod.CASH and next_stop.payment_status != PaymentStatus.PAID
    delivered_today = Order.objects.filter(
        courier=request.user, delivered_at__date=timezone.localdate()
    ).count()
    trip_total = delivered_today + len(stops)
    return render(
        request,
        "courier/route.html",
        {
            "start": start,
            "stops": stops,
            "next_stop": next_stop,
            "trip_total": trip_total,
            "trip_pct": round(delivered_today * 100 / trip_total) if trip_total else 0,
            "carrying": len(stops),
            "max_packages": store.max_packages_per_courier,
            "ready_count": sum(1 for o in ready if o.is_ready_to_ship),
            "cash_total": sum(o.cash_collected for o in cash),
            "cash_count": cash.count(),
            "delivered_today": delivered_today,
            "pet_trip": ServiceBooking.active_trip(request.user),
        },
    )


@roleRequired(Role.COURIER)
def route_data(request):
    """JSON untuk peta rute (diperbarui berkala tanpa memuat ulang halaman)."""
    start, stops = routing.route_for(request.user)
    return JsonResponse(
        {
            "courier": {"lat": start[0], "lng": start[1]},
            "store": {"lat": float(StoreSettings.current().latitude), "lng": float(StoreSettings.current().longitude)},
            "stops": [
                {
                    "id": o.pk,
                    "n": o.route_position,
                    "name": o.customer.name,
                    "address": o.delivery_address,
                    "lat": float(o.delivery_latitude) if o.has_pin else None,
                    "lng": float(o.delivery_longitude) if o.has_pin else None,
                    "km": round(o.cum_km, 1),
                    "eta": o.eta,
                    "cod": o.payment_method == PaymentMethod.CASH and o.payment_status != PaymentStatus.PAID,
                    "total": o.total_payment,
                    "handover_url": reverse("courier:handover", args=[o.pk]),
                }
                for o in stops
            ],
        }
    )


@roleRequired(Role.COURIER)
def reroute(request):
    if request.method == "POST":
        routing.reroute(request.user)
        messages.success(request, _("Rute dihitung ulang dari posisi Anda sekarang."))
    return redirect("courier:dashboard")


@roleRequired(Role.COURIER)
def pickup(request):
    """Scan QR label paket di toko: paket langsung berstatus Dalam Pengiriman."""
    if request.method == "POST":
        code = normalize_tracking_number(request.POST.get("code"))
        order = Order.objects.filter(tracking_number=code).select_related("customer").first() if code else None
        if order is None:
            messages.error(request, _("QR / resi tidak dikenal. Scan QR pada label paket."))
        elif _require_gps(request):
            try:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(pk=order.pk)
                    order.pickup_by(request.user)
                    routing.reroute(request.user, start=StoreSettings.current().location)
                last = CourierLocation.latest_for(request.user)
                order_event(
                    order, "Diambil kurir", request.user, detail=f"Scan label {order.tracking_number}",
                    lat=last.latitude if last else None, lng=last.longitude if last else None,
                    customer_title=f"Pesanan #{order.pk} dibawa kurir",
                    customer_body="Pantau posisi kurir secara langsung di peta.",
                )
                messages.success(request, f"Paket #{order.pk} ({order.customer.name}) masuk rute Anda.")
            except PetshopError as error:
                messages.error(request, str(error))
        return redirect("courier:pickup")
    store = StoreSettings.current()
    ready = [
        o for o in Order.objects.filter(
            Q(courier=request.user) | Q(courier__isnull=True),
            order_status=OrderStatus.CONFIRMED,
            packing_seq__isnull=False,
        ).select_related("customer").order_by("packing_date", "packing_seq")
        if o.is_ready_to_ship
    ]
    carrying = Order.objects.filter(courier=request.user, order_status=OrderStatus.ON_DELIVERY).select_related("customer").order_by("route_position")
    return render(
        request,
        "courier/pickup.html",
        {
            "ready": ready,
            "carrying": carrying,
            "max_packages": store.max_packages_per_courier,
            "pet_trip": ServiceBooking.active_trip(request.user),
        },
    )


def _my_delivery(request, pk):
    return get_object_or_404(
        Order.objects.select_related("customer").prefetch_related("details__product"),
        pk=pk, courier=request.user, order_status=OrderStatus.ON_DELIVERY,
    )


@roleRequired(Role.COURIER)
@require_POST
def check_handover(request, pk):
    """Langkah 1 serah terima: cocokkan QR dari HP pelanggan sebelum kamera dibuka."""
    order = _my_delivery(request, pk)
    ok = order.check_handover_code(request.POST.get("code"))
    return JsonResponse(
        {"ok": ok, "message": "QR cocok. Foto paket di tangan penerima." if ok else "QR / kode tidak cocok dengan paket ini."},
        status=200 if ok else 400,
    )


@roleRequired(Role.COURIER)
def handover(request, pk):
    """Serah terima: scan QR pelanggan -> foto paket di tangan penerima -> status Terkirim otomatis."""
    order = _my_delivery(request, pk)
    form = CameraPhotoForm(request.POST or None, request.FILES or None)
    cod = order.payment_method == PaymentMethod.CASH and order.payment_status != PaymentStatus.PAID
    if request.method == "POST":
        if not _require_gps(request):
            return redirect("courier:handover", pk=pk)
        if form.is_valid():
            data = form.cleaned_data
            try:
                order.handover(
                    request.user,
                    request.POST.get("code"),
                    data["photo"],
                    lat=data.get("latitude"),
                    lng=data.get("longitude"),
                    cash_received=bool(request.POST.get("cash_received")),
                )
            except PetshopError as error:
                messages.error(request, str(error))
            else:
                if data.get("note"):
                    Order.objects.filter(pk=order.pk).update(delivery_note=data["note"][:255])
                order_event(
                    order, "Diserahkan ke penerima", request.user,
                    detail="QR serah-terima cocok" + (f" · tunai Rp {order.cash_collected:,}".replace(",", ".") if order.cash_collected else ""),
                    photo=order.delivery_photo.name, lat=data.get("latitude"), lng=data.get("longitude"),
                    customer_title=f"Pesanan #{order.pk} sudah diterima",
                    customer_body="Terima kasih! Foto serah terima bisa dilihat di halaman lacak.",
                )
                routing.reroute(request.user)
                messages.success(request, f"Paket #{order.pk} selesai diantar.")
                return redirect("courier:dashboard")
        else:
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
    return render(request, "courier/handover.html", {"order": order, "form": form, "cod": cod})


@roleRequired(Role.COURIER)
def report_problem(request, pk):
    """Paket gagal diantar: kembali ke toko dengan catatan (+ foto opsional), admin & pelanggan diberi tahu."""
    order = _my_delivery(request, pk)
    form = ProblemForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if not form.is_valid():
            for errors in form.errors.values():
                for error in errors:
                    messages.error(request, error)
            return redirect("courier:problem", pk=pk)
        note, photo = form.cleaned_data["note"], form.cleaned_data["photo"]
        try:
            order.return_to_store(request.user, note)
        except PetshopError as error:
            messages.error(request, str(error))
            return redirect("courier:problem", pk=pk)
        last = CourierLocation.latest_for(request.user)
        order_event(
            order, "Gagal diantar, kembali ke toko", request.user, detail=note, photo=photo,
            lat=last.latitude if last else None, lng=last.longitude if last else None,
            customer_title=f"Pesanan #{order.pk} belum bisa diantar",
            customer_body=f"Kurir: {note}. Admin akan menghubungi Anda.",
        )
        Notification.to_staff(
            [Role.SUPERADMIN, Role.ADMIN, Role.CASHIER],
            f"Paket #{order.pk} gagal diantar",
            note,
            reverse("transaction:manage_transaction") + f"?q={order.pk}",
        )
        routing.reroute(request.user)
        messages.warning(request, f"Paket #{order.pk} dicatat kembali ke toko.")
        return redirect("courier:dashboard")
    return render(request, "courier/problem.html", {"order": order})


@roleRequired(Role.COURIER)
def cash(request):
    """Uang COD yang dipegang kurir + riwayat setoran ke kasir."""
    if request.method == "POST":
        try:
            remittance = CashRemittance.submit(request.user)
        except PetshopError as error:
            messages.error(request, str(error))
        else:
            Notification.to_staff(
                [Role.SUPERADMIN, Role.ADMIN, Role.CASHIER],
                f"Setoran COD dari {request.user.name}",
                f"Rp {remittance.amount:,}".replace(",", ".") + f" untuk {remittance.orders.count()} paket.",
                reverse("transaction:remittances"),
            )
            messages.success(request, _("Setoran dicatat. Serahkan uangnya ke kasir untuk dicocokkan."))
        return redirect("courier:cash")
    on_hand = Order.cash_on_hand(request.user).select_related("customer").order_by("delivered_at")
    return render(
        request,
        "courier/cash.html",
        {
            "on_hand": on_hand,
            "on_hand_total": sum(o.cash_collected for o in on_hand),
            "remittances": CashRemittance.objects.filter(courier=request.user).prefetch_related("orders")[:20],
        },
    )
