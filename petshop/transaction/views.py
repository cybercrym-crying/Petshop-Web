from urllib.parse import quote

from account.decorators import roleRequired
from django.utils.translation import gettext as _
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from common.cancel import MissingCancelReason, read_cancel_reason
from common.exceptions import PetshopError
from product.models import Product, InsufficientStock
from account.models import POS_ROLES, Customer, User, Role, person_search
from .notify import order_event
from store.models import StoreSettings
from .models import (
    Cart,
    CartItem,
    CheckoutError,
    InvalidTransition,
    Order,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)

# Kolom board = status order. Kolom terbuka tampil semua; kolom selesai dibatasi.
BOARD_COLUMNS = (
    (OrderStatus.PENDING, "pending", "Pesanan Online Baru"),
    (OrderStatus.CONFIRMED, "confirmed", "Dikonfirmasi"),
    (OrderStatus.ON_DELIVERY, "on-delivery", "Dalam Pengiriman"),
    (OrderStatus.DELIVERED, "delivered", "Terkirim"),
    (OrderStatus.CANCELLED, "cancelled", "Dibatalkan"),
)
OPEN_STATUSES = (OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.ON_DELIVERY)
CLOSED_COLUMN_LIMIT = 12


def _with_overdue(order):
    # Aturan telat bayar milik Order.is_overdue; di sini hanya disalin ke atribut
    # yang dibaca template.
    order.overdue = order.is_overdue
    return order


def _with_share_link(order, request):
    """Tautan WhatsApp berisi resi + link lacak, siap dikirim admin ke pelanggan."""
    track_url = request.build_absolute_uri(
        reverse("customer:track_detail", args=[order.tracking_number])
    )
    text = (
        f"Halo {order.customer.name}, pesanan Anda di Seelly Petshop "
        f"(order #{order.pk}) sudah kami proses.\n"
        f"No. resi: {order.tracking_number}\n"
        f"Lacak pesanan & lihat bukti pengiriman: {track_url}"
    )
    order.track_url = track_url
    order.share_wa_url = f"{order.customer.whatsapp_url}?text={quote(text)}"
    return order


def _get_or_create_cart(user):
    cart, _created = Cart.objects.get_or_create(user=user)
    return cart


@roleRequired(*POS_ROLES)
def add_to_cart(request, pk):
    if request.method == "POST":
        product = get_object_or_404(Product.objects.sellable(), pk=pk)
        cart = _get_or_create_cart(request.user)
        try:
            cart.add(product)
        except InsufficientStock:
            if product.stock <= 0:
                messages.error(request, f"Stok '{product.name}' habis.")
            else:
                messages.error(
                    request,
                    f"Stok '{product.name}' hanya {product.stock}, "
                    "semuanya sudah ada di keranjang.",
                )
        else:
            messages.success(request, f"'{product.name}' ditambahkan.")
    return redirect("transaction:make_transaction")


@roleRequired(*POS_ROLES)
def remove_from_cart(request, pk):
    if request.method == "POST":
        item = get_object_or_404(CartItem, pk=pk, cart__user=request.user)
        item.delete()
    return redirect("transaction:make_transaction")


@roleRequired(*POS_ROLES)
def update_cart_quantity(request, pk):
    if request.method == "POST":
        cart = get_object_or_404(Cart, user=request.user)
        item = get_object_or_404(cart.items, pk=pk)
        step = request.POST.get("step")
        try:
            # Tombol - / + di layar kasir mengirim "step"; kolom angka mengirim "quantity". 0 = hapus.
            quantity = item.quantity + int(step) if step in ("-1", "1") else int(request.POST.get("quantity", ""))
        except ValueError:
            messages.error(request, _("Jumlah harus berupa angka."))
            return redirect("transaction:make_transaction")
        try:
            cart.set_quantity(item.pk, quantity)
        except InsufficientStock as e:
            messages.error(request, str(e))
    return redirect("transaction:make_transaction")


@roleRequired(*POS_ROLES)
def cancel_transaction(request):
    if request.method == "POST":
        Cart.objects.filter(user=request.user).delete()
        messages.success(request, _("Transaksi dibatalkan."))
    return redirect("transaction:make_transaction")


@roleRequired(*POS_ROLES)
def manage_transaction(request):
    cancelled = Order.cancel_expired()
    if cancelled:
        messages.info(request, f"{cancelled} pesanan transfer dibatalkan otomatis karena lewat batas bayar.")
    view = "list" if request.GET.get("view") == "list" else "board"
    q = request.GET.get("q", "").strip()
    only_unpaid = request.GET.get("payment") == "pending"
    only_proof = request.GET.get("payment") == "proof"

    orders = (
        Order.objects.select_related("customer", "admin", "courier")
        .prefetch_related("details__product")
        .order_by("-date")
    )
    if q:
        orders, cond = person_search(orders, q, prefix="customer__")
        cond |= Q(tracking_number__icontains=q)
        digits = q.lstrip("#")
        if digits.isdigit() and len(digits) <= 9:
            cond |= Q(pk=int(digits))
        orders = orders.filter(cond)
    if only_unpaid or only_proof:
        orders = orders.filter(payment_status=PaymentStatus.PENDING).exclude(
            order_status=OrderStatus.CANCELLED
        )
    if only_proof:
        orders = orders.exclude(payment_proof="").exclude(payment_proof__isnull=True)

    columns = []
    if view == "board":
        for status, css, title in BOARD_COLUMNS:
            qs = orders.filter(order_status=status)
            count = qs.count()
            is_open = status in OPEN_STATUSES
            shown = [
                _with_share_link(_with_overdue(o), request)
                for o in (qs if is_open else qs[:CLOSED_COLUMN_LIMIT])
            ]
            columns.append(
                {
                    "css": css,
                    "title": title,
                    "count": count,
                    "orders": shown,
                    "total": sum(o.total_payment for o in shown) if is_open else None,
                    "hidden": count - len(shown),
                }
            )
        # Tab yang terbuka pertama: pesanan online baru bila ada, selain itu Dikonfirmasi.
        active = next(
            (c for c in columns if c["css"] == "pending" and c["count"]),
            next(c for c in columns if c["css"] == "confirmed"),
        )
        for col in columns:
            col["active"] = col is active
        transactions = [o for col in columns for o in col["orders"]]
    else:
        transactions = [_with_share_link(_with_overdue(o), request) for o in orders]

    active = Order.objects.filter(order_status__in=OPEN_STATUSES).aggregate(
        n=Count("pk"), total=Sum("total_payment")
    )
    overdue_unpaid = sum(
        1
        for o in Order.objects.filter(payment_status=PaymentStatus.PENDING).exclude(
            order_status=OrderStatus.CANCELLED
        )
        if o.is_overdue
    )

    return render(
        request,
        "transaction/manage_transaction.html",
        {
            "view": view,
            "q": q,
            "only_unpaid": only_unpaid,
            "columns": columns,
            "transactions": transactions,  # dipakai tabel (list) dan modal detail
            "active": active,
            "overdue_unpaid": overdue_unpaid,
            "proof_orders": list(_proof_waiting().select_related("customer").order_by("payment_proof_at")[:20]),
            "refund_orders": list(Order.objects.filter(refund_due__gt=0).select_related("customer").order_by("cancelled_at")[:20]),
            "only_proof": only_proof,
            "couriers": User.couriers(),
        },
    )


def _proof_waiting():
    return (
        Order.objects.filter(payment_status=PaymentStatus.PENDING)
        .exclude(order_status=OrderStatus.CANCELLED)
        .exclude(payment_proof="")
        .exclude(payment_proof__isnull=True)
    )


@roleRequired(*POS_ROLES)
def payment_check(request, pk):
    """Cek bukti transfer: cocokkan dengan mutasi rekening lalu setujui atau tolak."""
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    if request.method == "POST":
        decision = request.POST.get("decision")
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=pk)
                if decision == "approve":
                    order.verify_payment(request.user)
                    order_event(
                        order, "Pembayaran diverifikasi", request.user,
                        customer_title=f"Pembayaran pesanan #{order.pk} diterima",
                        customer_body="Pesanan Anda masuk antrean packing.",
                    )
                    messages.success(request, f"Order #{order.pk} lunas dan masuk antrean packing.")
                elif decision == "reject":
                    note = request.POST.get("note", "")
                    order.reject_payment(request.user, note)
                    order_event(
                        order, "Bukti transfer ditolak", request.user, detail=note,
                        customer_title=f"Bukti transfer pesanan #{order.pk} perlu dikirim ulang",
                        customer_body=note,
                    )
                    messages.warning(request, f"Bukti order #{order.pk} ditolak; pelanggan diminta kirim ulang.")
                else:
                    messages.error(request, _("Aksi tidak dikenal."))
        except InvalidTransition as e:
            messages.error(request, str(e))
            return redirect("transaction:payment_check", pk=pk)
        return redirect(f"{reverse('transaction:manage_transaction')}?payment=proof")
    return render(
        request,
        "transaction/payment_check.html",
        {
            "order": order,
            "waiting": _proof_waiting().exclude(pk=order.pk).order_by("payment_proof_at")[:10],
            "queue": _proof_waiting().select_related("customer").order_by("payment_proof_at")[:12],
            "details": order.details.select_related("product"),
            "bank_accounts": StoreSettings.current().bank_accounts(),
        },
    )


def _packing_queue():
    return (
        Order.objects.filter(order_status=OrderStatus.CONFIRMED, packing_seq__isnull=False)
        .select_related("customer", "courier")
        .prefetch_related("details__product")
        .order_by("packed_at", "packing_date", "packing_seq")
    )


@roleRequired(*POS_ROLES)
def packing_queue(request):
    """Antrean packing: urut nomor packing; kasir mengemas, mencetak label, lalu menandai siap diambil kurir."""
    Order.cancel_expired()
    queue = list(_packing_queue())
    return render(
        request,
        "transaction/packing_queue.html",
        {
            "to_pack": [o for o in queue if not o.packed_at],
            "packed": [o for o in queue if o.packed_at],
            "couriers": User.couriers(),
        },
    )


@roleRequired(*POS_ROLES)
def print_label(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer", "courier").prefetch_related("details__product"), pk=pk
    )
    return render(request, "transaction/label.html", {"order": order})


@roleRequired(*POS_ROLES)
def label_qr(request, pk):
    from .qr import qr_response

    order = get_object_or_404(Order, pk=pk)
    return qr_response(order.tracking_number)


@roleRequired(*POS_ROLES)
def update_status(request, pk):
    if request.method != "POST":
        return redirect("transaction:manage_transaction")

    action = request.POST.get("action")
    try:
        with transaction.atomic():
            order = get_object_or_404(Order.objects.select_for_update(), pk=pk)
            if action == "confirm":
                order.confirm(request.user)
                order_event(
                    order, "Dikonfirmasi toko", request.user,
                    customer_title=f"Pesanan #{order.pk} dikonfirmasi",
                    customer_body=(
                        f"Nomor packing {order.packing_label}." if order.packing_seq
                        else "Silakan selesaikan pembayaran transfer."
                    ),
                )
                messages.success(
                    request, f"Pesanan online #{order.pk} dikonfirmasi."
                )
            elif action == "paid":
                order.verify_payment(request.user)
                order_event(
                    order, "Ditandai lunas", request.user,
                    customer_title=f"Pembayaran pesanan #{order.pk} diterima",
                )
                messages.success(request, f"Order #{order.pk} ditandai lunas.")
            elif action == "packed":
                order.mark_packed(request.user)
                order_event(order, "Selesai dikemas", request.user)
                messages.success(request, f"Order #{order.pk} siap diambil kurir.")
            elif action == "assign_courier":
                courier = User.couriers().filter(
                    pk=request.POST.get("courier") or None
                ).first()
                order.assign_courier(courier)
                order_event(order, "Kurir ditugaskan", request.user, detail=courier.name)
                messages.success(
                    request,
                    f"Kurir {courier.get_full_name() or courier.username} "
                    f"ditugaskan ke order #{order.pk}.",
                )
            elif action == "delivered":
                order.mark_delivered()
                order_event(order, "Ditutup manual oleh toko", request.user)
                messages.success(request, f"Order #{order.pk} selesai diantar.")
            elif action == "cancel":
                if order.receipt_no:
                    # Transaksi kasir: hanya admin, wajib alasan (lihat pos.void).
                    raise InvalidTransition(
                        f"Order #{order.pk} adalah transaksi kasir: batalkan lewat halaman struk (admin, dengan alasan)."
                    )
                reason = read_cancel_reason(request.POST)
                order.cancel(reason=reason, by=request.user)
                order_event(
                    order, "Dibatalkan toko", request.user, detail=reason,
                    customer_title=f"Pesanan #{order.pk} dibatalkan toko", customer_body=reason,
                )
                messages.success(
                    request, f"Order #{order.pk} dibatalkan, stok dikembalikan."
                )
                if order.payment_status == PaymentStatus.PAID:
                    messages.warning(
                        request, _("Order sudah lunas: kembalikan dana ke pelanggan.")
                    )
            else:
                messages.error(request, _("Aksi tidak dikenal."))
    except (InvalidTransition, MissingCancelReason) as e:
        messages.error(request, str(e))
    if request.POST.get("next") == "packing":
        return redirect("transaction:packing_queue")
    return redirect("transaction:manage_transaction")


@roleRequired(*POS_ROLES)
def remittances(request):
    """Kasir menerima setoran uang COD dari kurir dan mencatat selisih bila ada."""
    from courier.models import CashRemittance, RemittanceStatus

    if request.method == "POST":
        remittance = get_object_or_404(CashRemittance, pk=request.POST.get("remittance"))
        try:
            amount = int(str(request.POST.get("received_amount", "")).replace(".", "").strip())
        except ValueError:
            amount = None
        try:
            remittance.receive(request.user, amount, request.POST.get("note", ""))
        except PetshopError as e:
            messages.error(request, str(e))
        else:
            from store.models import ActivityLog, Notification

            ActivityLog.record(remittance, "Setoran diterima kasir", request.user,
                               detail=f"Rp {amount:,}".replace(",", "."))
            Notification.send(remittance.courier, f"Setoran #{remittance.pk} diterima kasir",
                              f"Rp {amount:,}".replace(",", "."), reverse("courier:cash"))
            messages.success(request, f"Setoran #{remittance.pk} dari {remittance.courier.name} diterima.")
        return redirect("transaction:remittances")
    from service.models import ServiceBooking

    pending = (
        CashRemittance.objects.filter(status=RemittanceStatus.SUBMITTED)
        .select_related("courier").prefetch_related("orders__customer", "bookings__customer")
    )
    # Uang COD yang masih dipegang kurir: paket + booking hewan, dijumlah per kurir.
    held = {}
    for qs, field in (
        (Order.objects.filter(cash_collected__gt=0, remittance__isnull=True), "courier"),
        (ServiceBooking.objects.filter(cash_collected__gt=0, remittance__isnull=True), "pet_courier"),
    ):
        rows = qs.values(f"{field}_id", f"{field}__first_name", f"{field}__last_name", f"{field}__username").annotate(
            total=Sum("cash_collected"), n=Count("pk")
        )
        for row in rows:
            key = row[f"{field}_id"]
            entry = held.setdefault(key, {
                "courier__first_name": row[f"{field}__first_name"],
                "courier__last_name": row[f"{field}__last_name"],
                "courier__username": row[f"{field}__username"],
                "total": 0, "n": 0,
            })
            entry["total"] += row["total"]
            entry["n"] += row["n"]
    on_hand = sorted(held.values(), key=lambda r: -r["total"])
    done = CashRemittance.objects.filter(status=RemittanceStatus.RECEIVED).select_related("courier", "received_by")[:20]
    return render(request, "transaction/remittances.html", {"pending": pending, "on_hand": on_hand, "done": done})
