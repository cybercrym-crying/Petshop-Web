"""Transaksi kasir (offline): bayar di tempat, struk, diskon, pajak, shift, parkir, retur, pembatalan.

Semua aturan uang & stok ada di sini supaya view tetap tipis dan mudah dites.
"""

import secrets
from decimal import ROUND_HALF_UP, Decimal

from django.db import models, transaction
from django.utils import timezone

from account.models import ADMIN_ROLES, User
from product.models import MutationType, Product
from store.models import ActivityLog, Notification, StoreSettings

from .models import (
    COUNTER_PAYMENT_METHODS,
    Cart,
    CartService,
    CashierShift,
    CheckoutError,
    Fulfillment,
    HeldSale,
    InvalidTransition,
    Order,
    OrderChannel,
    OrderDetail,
    OrderPayment,
    OrderServiceLine,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ReturnLine,
    ReturnRequest,
    ReturnStatus,
)

MAX_HELD_SALES = 10
RECEIPT_TOKEN_BYTES = 12


class PosError(CheckoutError):
    pass


# ---------------------------------------------------------------- shift kasir


def open_shift(user, opening_cash):
    if CashierShift.current(user):
        raise PosError("Kasir Anda sudah dibuka.")
    if opening_cash is None or opening_cash < 0:
        raise PosError("Isi modal awal uang di laci (boleh 0).")
    shift = CashierShift.objects.create(cashier=user, opening_cash=opening_cash)
    ActivityLog.record(shift, "Kasir dibuka", actor=user, detail=f"Modal awal Rp {opening_cash:,}".replace(",", "."))
    return shift


def require_shift(user):
    shift = CashierShift.current(user)
    if shift is None:
        raise PosError("Buka kasir dulu (isi modal awal laci) sebelum menerima pembayaran.")
    return shift


# ---------------------------------------------------------------- layanan grooming

# Booking yang sudah check-in boleh dibayar (umumnya dibayar saat hewan diambil).
PAYABLE_BOOKING_STATUSES = ("ANTRE", "PROSES", "SIAP", "DIANTAR", "SELESAI")


def ensure_booking_payable(booking):
    if booking.status not in PAYABLE_BOOKING_STATUSES:
        raise PosError(
            f"Booking #{booking.pk} berstatus {booking.get_status_display()}: "
            "bisa dibayar setelah hewan check-in."
        )
    if booking.is_paid:
        raise PosError(f"Booking #{booking.pk} sudah dibayar (struk {booking.payment_line.order.receipt_no}).")


def find_booking(code):
    """Cari booking dari isi QR ('PSB:<id>:<kode>') atau '#123'."""
    from service.models import ServiceBooking

    raw = (code or "").strip()
    if raw.upper().startswith("PSB:"):
        return ServiceBooking.find_by_code(raw)
    digits = raw.lstrip("#")
    if digits.isdigit():
        return ServiceBooking.objects.filter(pk=int(digits)).first()
    return None


def find_product(code):
    """Produk dari kode barang (SKU/barcode), tanpa beda huruf besar/kecil & spasi."""
    code = "".join((code or "").split())
    if not code:
        return None
    return Product.objects.sellable().filter(sku__iexact=code).first()


def assign_codes():
    """Beri kode SLY-0001 dst. ke produk yang belum punya kode barang. Mengembalikan jumlahnya."""
    made = 0
    for product in Product.objects.filter(sku__isnull=True).order_by("pk"):
        candidate, n = f"SLY-{product.pk:04d}", 2
        while Product.objects.filter(sku=candidate).exists():
            candidate = f"SLY-{product.pk:04d}-{n}"
            n += 1
        Product.objects.filter(pk=product.pk).update(sku=candidate)
        made += 1
    return made


# ---------------------------------------------------------------- hitungan


def calc_tax(base, percent):
    if not percent or base <= 0:
        return 0
    value = (Decimal(base) * Decimal(percent) / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(value)


def quote(cart, discount=0, shipping_fee=0, store=None):
    """Rincian angka sebelum dibayar (dipakai layar kasir & checkout)."""
    store = store or StoreSettings.current()
    goods = cart.goods_total
    services = cart.services_total
    subtotal = goods + services
    discount = max(0, min(int(discount or 0), subtotal))
    tax = calc_tax(subtotal - discount, store.tax_percent)
    total = subtotal - discount + tax + int(shipping_fee or 0)
    return {
        "goods": goods, "services": services, "subtotal": subtotal, "discount": discount,
        "tax_percent": store.tax_percent, "tax": tax, "shipping_fee": int(shipping_fee or 0), "total": total,
    }


def _new_receipt_no():
    today = timezone.localdate()
    prefix = f"STR-{today:%y%m%d}-"
    last = (
        Order.objects.select_for_update()
        .filter(receipt_no__startswith=prefix)
        .order_by("-receipt_no")
        .values_list("receipt_no", flat=True)
        .first()
    )
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


def _new_receipt_token():
    while True:
        token = secrets.token_urlsafe(RECEIPT_TOKEN_BYTES)
        if not Order.objects.filter(receipt_token=token).exists():
            return token


# ---------------------------------------------------------------- bayar


@transaction.atomic
def checkout(
    cart,
    cashier,
    *,
    customer=None,
    buyer_name="",
    buyer_phone="",
    fulfillment=Fulfillment.TAKE_AWAY,
    courier=None,
    shipping_fee=0,
    discount=0,
    discount_reason="",
    pay_transfer=0,
    pay_qris=0,
    cash_received=0,
    noncash_confirmed=False,
    note="",
):
    """Bayar transaksi kasir. Mengembalikan Order yang langsung lunas.

    Pembayaran: transfer dan/atau QRIS (nominal diisi kasir setelah dicek masuk),
    sisanya tunai. Tunai: uang diterima >= sisa, kembalian dihitung otomatis.
    """
    store = StoreSettings.current()
    shift = require_shift(cashier)
    cart = Cart.objects.select_for_update().get(pk=cart.pk)
    items = list(cart.items.select_related("product"))
    service_rows = list(cart.services.select_related("booking__service", "booking__customer"))
    if not items and not service_rows:
        raise PosError("Belum ada barang atau layanan di transaksi.")

    walk_in = customer is None
    customer = customer or User.walk_in()
    if fulfillment not in Fulfillment.values:
        raise PosError("Pilih: dibawa langsung atau diantar.")
    pin = {}
    if fulfillment == Fulfillment.DELIVERY:
        if walk_in:
            raise PosError("Untuk diantar, pilih pelanggan terdaftar (alamat & nomor HP tersimpan).")
        if not items:
            raise PosError("Tidak ada barang yang perlu diantar.")
        if not (customer.address or "").strip():
            raise PosError(f"Alamat {customer.name} kosong. Lengkapi dulu di Kelola Akun.")
        if courier is not None and courier.role != "KURIR":
            courier = None
        last = (
            Order.objects.filter(customer=customer, delivery_latitude__isnull=False)
            .order_by("-date").values_list("delivery_latitude", "delivery_longitude").first()
        )
        if last:
            distance = store.distance_km(*last)
            pin = {"delivery_latitude": last[0], "delivery_longitude": last[1],
                   "delivery_distance_km": round(distance, 2)}
            if not shipping_fee:
                shipping_fee = store.shipping_fee(distance)
    else:
        courier, shipping_fee = None, 0

    numbers = quote(cart, discount, shipping_fee, store)
    discount = int(discount or 0)
    if discount < 0 or discount > numbers["subtotal"]:
        raise PosError("Diskon tidak boleh melebihi total belanja.")
    discount_reason = (discount_reason or "").strip()
    if discount and not discount_reason:
        raise PosError("Tulis alasan diskon.")
    if discount > store.cashier_discount_limit and cashier.role not in ADMIN_ROLES:
        raise PosError(
            f"Diskon di atas Rp {store.cashier_discount_limit:,} harus diberikan Admin.".replace(",", ".")
        )

    total = numbers["total"]
    pay_transfer, pay_qris = int(pay_transfer or 0), int(pay_qris or 0)
    if pay_transfer < 0 or pay_qris < 0:
        raise PosError("Nominal pembayaran tidak valid.")
    noncash = pay_transfer + pay_qris
    if noncash > total:
        raise PosError("Nominal transfer/QRIS melebihi total yang harus dibayar.")
    if noncash and not noncash_confirmed:
        raise PosError("Pastikan dana transfer/QRIS sudah masuk ke rekening toko, lalu centang konfirmasinya.")
    cash_due = total - noncash
    cash_received = int(cash_received or 0)
    if cash_due and cash_received < cash_due:
        raise PosError(f"Uang tunai kurang: harus Rp {cash_due:,}.".replace(",", "."))
    if not cash_due:
        cash_received = 0
    parts = [(m, a) for m, a in (
        (PaymentMethod.CASH, cash_due), (PaymentMethod.TRANSFER, pay_transfer), (PaymentMethod.QRIS, pay_qris)
    ) if a > 0]
    if not parts:
        parts = [(PaymentMethod.CASH, 0)]  # transaksi Rp 0 (mis. diskon penuh) tetap tercatat tunai
    method = parts[0][0] if len(parts) == 1 else PaymentMethod.MIXED

    now = timezone.now()
    take_away = fulfillment == Fulfillment.TAKE_AWAY
    order = Order.objects.create(
        admin=cashier,
        customer=customer,
        channel=OrderChannel.STORE,
        fulfillment=fulfillment,
        order_status=OrderStatus.DELIVERED if take_away else OrderStatus.CONFIRMED,
        delivered_at=now if take_away else None,
        payment_method=method,
        payment_status=PaymentStatus.PAID,
        payment_verified_by=cashier,
        payment_verified_at=now,
        confirmed_at=now,
        courier=courier,
        shipping_address=customer.address if not take_away else "",
        shipping_fee=numbers["shipping_fee"],
        customer_note=(note or "").strip()[:255],
        buyer_name=(buyer_name or "").strip()[:80] if walk_in else "",
        buyer_phone=(buyer_phone or "").strip()[:20] if walk_in else "",
        discount=discount,
        discount_reason=discount_reason[:160],
        discount_by=cashier if discount else None,
        tax_percent=numbers["tax_percent"],
        tax_amount=numbers["tax"],
        cash_received=cash_received,
        change_given=cash_received - cash_due if cash_due else 0,
        shift=shift,
        receipt_no=_new_receipt_no(),
        receipt_token=_new_receipt_token(),
        **pin,
    )
    for item in items:
        product = item.product
        if not product.isSellable:
            raise PosError(f"'{product.name}' tidak dijual.")
        product.apply_mutation(MutationType.OUT, item.quantity, user=cashier, note=f"Struk {order.receipt_no}")
        OrderDetail.objects.create(
            transaction=order, product=product, quantity=item.quantity,
            unit_price=product.selling_price, subtotal=item.subtotal,
        )
    for row in service_rows:
        booking = type(row.booking).objects.select_for_update().get(pk=row.booking_id)
        ensure_booking_payable(booking)
        OrderServiceLine.objects.create(
            order=order, booking=booking,
            description=f"{booking.service.name} · {booking.pet_name} (booking #{booking.pk})"[:160],
            amount=booking.total_price,
        )
    for method_code, amount in parts:
        OrderPayment.objects.create(order=order, method=method_code, amount=amount)
    order.total_payment = total
    order.save(update_fields=["total_payment"])
    if not take_away:
        order.queue_for_packing()
    cart.delete()
    ActivityLog.record(
        order, "Transaksi kasir", actor=cashier,
        detail=f"{order.receipt_no} · {Fulfillment(fulfillment).label} · Rp {total:,}".replace(",", "."),
    )
    if discount:
        ActivityLog.record(order, "Diskon", actor=cashier, detail=f"Rp {discount:,} · {discount_reason}".replace(",", "."))
    return order


# ---------------------------------------------------------------- parkir


@transaction.atomic
def hold(cart, cashier, label=""):
    if cart.is_empty:
        raise PosError("Transaksi masih kosong, tidak ada yang diparkir.")
    if HeldSale.objects.filter(cashier=cashier).count() >= MAX_HELD_SALES:
        raise PosError(f"Maksimal {MAX_HELD_SALES} transaksi diparkir. Lanjutkan atau hapus yang lama.")
    held = HeldSale.objects.create(
        cashier=cashier,
        label=(label or "").strip()[:60],
        lines=[[i.product_id, i.quantity] for i in cart.items.all()],
        bookings=list(cart.services.values_list("booking_id", flat=True)),
        total=cart.total,
    )
    cart.items.all().delete()
    cart.services.all().delete()
    return held


@transaction.atomic
def resume(held, cashier):
    """Kembalikan transaksi parkir ke layar kasir. Mengembalikan daftar peringatan."""
    if held.cashier_id != cashier.pk:
        raise PosError("Transaksi parkir ini milik kasir lain.")
    cart, _created = Cart.objects.get_or_create(user=cashier)
    if not cart.is_empty:
        raise PosError("Selesaikan atau parkir transaksi yang sedang berjalan dulu.")
    warnings = []
    products = Product.objects.sellable().in_bulk([pid for pid, _q in held.lines])
    for product_id, qty in held.lines:
        product = products.get(product_id)
        if product is None:
            warnings.append(f"Produk #{product_id} sudah tidak dijual, dilewati.")
            continue
        qty = min(qty, product.stock)
        if qty <= 0:
            warnings.append(f"Stok '{product.name}' habis, dilewati.")
            continue
        if qty < dict(held.lines).get(product_id, qty):
            warnings.append(f"Stok '{product.name}' tinggal {qty}.")
        cart.items.create(product=product, quantity=qty)
    from service.models import ServiceBooking

    for booking in ServiceBooking.objects.filter(pk__in=held.bookings):
        try:
            cart.add_service(booking)
        except PosError as e:
            warnings.append(str(e))
    held.delete()
    return warnings


# ---------------------------------------------------------------- batal (admin)


@transaction.atomic
def void(order, admin, reason):
    """Admin membatalkan transaksi kasir: stok kembali, booking kembali belum dibayar."""
    if admin.role not in ADMIN_ROLES:
        raise InvalidTransition("Pembatalan transaksi kasir hanya oleh Admin/Super Admin.")
    reason = (reason or "").strip()
    if not reason:
        raise InvalidTransition("Tulis alasan pembatalan.")
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.channel != OrderChannel.STORE:
        raise InvalidTransition(f"Order #{order.pk} bukan transaksi kasir.")
    if order.order_status == OrderStatus.CANCELLED:
        raise InvalidTransition(f"Order #{order.pk} sudah dibatalkan.")
    if order.order_status == OrderStatus.ON_DELIVERY:
        raise InvalidTransition(f"Order #{order.pk} sedang diantar kurir; tunggu kembali ke toko.")
    if order.returns.exclude(status=ReturnStatus.REJECTED).exists():
        raise InvalidTransition(f"Order #{order.pk} sudah punya retur; selesaikan lewat retur.")
    order.order_status = OrderStatus.CANCELLED
    order.voided_at = timezone.now()
    order.voided_by = admin
    order.void_reason = reason[:255]
    order.route_position = None
    order.save(update_fields=["order_status", "voided_at", "voided_by", "void_reason", "route_position"])
    for detail in order.details.select_related("product"):
        detail.product.apply_mutation(
            MutationType.IN, detail.quantity, user=admin,
            note=f"Struk {order.receipt_no or order.pk} dibatalkan",
        )
    ActivityLog.record(order, "Dibatalkan admin", actor=admin, detail=reason)
    return order


# ---------------------------------------------------------------- retur


def returnable_qty(detail):
    taken = (
        ReturnLine.objects.filter(detail=detail)
        .exclude(request__status=ReturnStatus.REJECTED)
        .aggregate(t=models.Sum("quantity"))["t"]
        or 0
    )
    return detail.quantity - taken


def return_deadline(order, store=None):
    store = store or StoreSettings.current()
    base = order.delivered_at or order.date
    return base + timezone.timedelta(days=store.return_days)


def can_return(order):
    return (
        order.order_status == OrderStatus.DELIVERED
        and order.payment_status == PaymentStatus.PAID
        and timezone.now() <= return_deadline(order)
    )


@transaction.atomic
def request_return(order, user, quantities, reason, refund_method=PaymentMethod.CASH):
    """quantities: {detail_id: jumlah}. Nilai uang kembali dihitung proporsional terhadap diskon & pajak."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.order_status != OrderStatus.DELIVERED or order.payment_status != PaymentStatus.PAID:
        raise PosError("Retur hanya untuk transaksi lunas yang barangnya sudah diterima.")
    if timezone.now() > return_deadline(order):
        raise PosError(f"Batas retur {StoreSettings.current().return_days} hari sudah lewat.")
    reason = (reason or "").strip()
    if not reason:
        raise PosError("Tulis alasan retur (mis. rusak, salah ukuran).")
    if refund_method not in COUNTER_PAYMENT_METHODS:
        raise PosError("Pilih cara pengembalian uang.")
    details = {d.pk: d for d in order.details.select_related("product")}
    wanted = []
    for detail_id, qty in quantities.items():
        try:
            detail_id, qty = int(detail_id), int(qty)
        except (TypeError, ValueError):
            raise PosError("Jumlah retur tidak valid.")
        if qty <= 0:
            continue
        detail = details.get(detail_id)
        if detail is None:
            raise PosError("Barang retur tidak ada di transaksi ini.")
        if qty > returnable_qty(detail):
            raise PosError(f"'{detail.product.name}' maksimal {returnable_qty(detail)} pcs yang bisa diretur.")
        wanted.append((detail, qty))
    if not wanted:
        raise PosError("Pilih barang dan jumlah yang diretur.")
    subtotal = order.subtotal_before_discount
    paid_for_goods = order.total_payment - order.shipping_fee
    factor = Decimal(paid_for_goods) / Decimal(subtotal) if subtotal else Decimal(1)
    req = ReturnRequest.objects.create(order=order, requested_by=user, reason=reason[:255], refund_method=refund_method)
    total = 0
    for detail, qty in wanted:
        amount = int((Decimal(detail.unit_price * qty) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        ReturnLine.objects.create(request=req, detail=detail, quantity=qty, amount=amount)
        total += amount
    req.refund_amount = total
    req.save(update_fields=["refund_amount"])
    ActivityLog.record(order, "Retur diajukan", actor=user, detail=f"Rp {total:,} · {reason}".replace(",", "."))
    Notification.to_staff(
        ADMIN_ROLES, f"Retur menunggu persetujuan ({order.receipt_no or '#' + str(order.pk)})",
        f"Rp {total:,} · {reason}".replace(",", "."), "/staff/admin/retur/",
    )
    return req


@transaction.atomic
def decide_return(req, admin, approve, note=""):
    if admin.role not in ADMIN_ROLES:
        raise InvalidTransition("Retur hanya bisa disetujui Admin/Super Admin.")
    req = ReturnRequest.objects.select_for_update().get(pk=req.pk)
    if req.status != ReturnStatus.PENDING:
        raise InvalidTransition("Retur ini sudah diputuskan.")
    note = (note or "").strip()
    req.decided_by = admin
    req.decided_at = timezone.now()
    req.decision_note = note[:255]
    if not approve:
        if not note:
            raise InvalidTransition("Tulis alasan penolakan.")
        req.status = ReturnStatus.REJECTED
        req.save()
        ActivityLog.record(req.order, "Retur ditolak", actor=admin, detail=note)
        return req
    for line in req.lines.select_related("detail__product"):
        line.detail.product.apply_mutation(
            MutationType.IN, line.quantity, user=admin, note=f"Retur {req.order.receipt_no or req.order.pk}"
        )
    req.status = ReturnStatus.APPROVED
    if req.refund_method == PaymentMethod.CASH:
        req.refund_shift = CashierShift.current(req.requested_by) or CashierShift.current(admin)
    req.save()
    ActivityLog.record(
        req.order, "Retur disetujui", actor=admin,
        detail=f"Uang kembali Rp {req.refund_amount:,} ({req.get_refund_method_display()})".replace(",", "."),
    )
    Notification.send(
        req.requested_by, "Retur disetujui",
        f"{req.order.receipt_no}: kembalikan Rp {req.refund_amount:,} ke pembeli.".replace(",", "."),
        "/staff/admin/retur/",
    )
    return req


# Dipakai seed & tes: CartService tidak perlu diimpor dari tempat lain.
__all__ = [
    "PosError", "open_shift", "require_shift", "checkout", "hold", "resume", "void",
    "request_return", "decide_return", "returnable_qty", "can_return", "find_product",
    "find_booking", "ensure_booking_payable", "quote", "assign_codes", "CartService",
]
