"""Halaman kasir (transaksi offline): layar kasir, shift, parkir, struk, batal, retur, laporan."""

import csv
from urllib.parse import quote as urlquote

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db.models import Count
from django.views.decorators.http import require_POST

from account.dashboard import Period, parse_range
from account.decorators import roleRequired
from account.form import QuickCustomerForm
from account.models import ADMIN_ROLES, POS_ROLES, Customer, Role, User
from common.exceptions import PetshopError
from product.models import Category, InsufficientStock, Product
from store.models import ActivityLog, StoreSettings

from . import pos
from .models import (
    COUNTER_PAYMENT_METHODS,
    Cart,
    CartService,
    CashierShift,
    Fulfillment,
    HeldSale,
    Order,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ReturnRequest,
    ReturnStatus,
)
from .qr import qr_response
from .reports import cashier_report, counter_sales

REPORT_RANGES = (1, 7, 30, 90)


def _int(value, default=0):
    try:
        return int(str(value or "").replace(".", "").replace(",", "").strip() or default)
    except ValueError:
        return None


def _cart(user):
    cart, _created = Cart.objects.get_or_create(user=user)
    return cart


@roleRequired(*POS_ROLES)
@require_POST
def quick_customer(request):
    """Kasir mendaftarkan pelanggan baru (nama, WA, alamat, titik peta) tanpa menunggu admin, lalu
    pelanggan itu langsung terpilih di layar kasir atau form Buat Booking."""
    form = QuickCustomerForm(request.POST)
    if not form.is_valid():
        errors = {field: [str(e) for e in errs] for field, errs in form.errors.items()}
        return JsonResponse({"errors": errors}, status=400)
    customer = form.save()
    ActivityLog.record(customer, "Pelanggan baru dari kasir", actor=request.user, detail=customer.phone_number)
    fee = pos.auto_shipping_fees([customer], StoreSettings.current())[customer.pk]
    return JsonResponse({
        "pk": customer.pk,
        "label": f"{customer.name} ({customer.phone_number})",
        "address": customer.address,
        "lat": "" if customer.latitude is None else str(customer.latitude),
        "lng": "" if customer.longitude is None else str(customer.longitude),
        "ship": fee,
    })


@roleRequired(*POS_ROLES)
def make_transaction(request):
    cart = _cart(request.user)
    products = Product.objects.sellable().select_related("category")
    q = (request.GET.get("q") or "").strip()
    if q:
        products = products.filter(name__icontains=q) | products.filter(sku__iexact=q)
    categories = Category.objects.filter(
        pk__in=Product.objects.sellable().values("category_id")
    ).order_by("name")
    cat = request.GET.get("cat") or ""
    if cat.isdigit():
        products = products.filter(category_id=int(cat))
    store = StoreSettings.current()
    cart_services = list(cart.services.select_related("booking__service", "booking__customer"))
    cart_items = list(cart.items.select_related("product"))
    customers = list(Customer.objects.order_by("first_name", "last_name"))
    fees = pos.auto_shipping_fees(customers, store)
    for c in customers:
        c.auto_ship = fees[c.pk]
    return render(
        request,
        "transaction/make_transaction.html",
        {
            "products": products.distinct(),
            "q": q,
            "categories": categories,
            "cat": int(cat) if cat.isdigit() else None,
            "cart_items": cart_items,
            "cart_count": len(cart_items) + len(cart_services),
            "cart_services": cart_services,
            "numbers": pos.quote(cart, store=store),
            "cart_empty": cart.is_empty,
            "customers": customers,
            "couriers": User.couriers().filter(is_active=True),
            "shift": CashierShift.current(request.user),
            "held_sales": HeldSale.objects.filter(cashier=request.user),
            "store": store,
            "fulfillments": Fulfillment.choices,
        },
    )


@roleRequired(*POS_ROLES)
@require_POST
def scan(request):
    """Satu kotak untuk scanner USB / kamera: kode barang, QR booking (PSB:...), atau #booking."""
    code = (request.POST.get("code") or "").strip()
    cart = _cart(request.user)
    product = pos.find_product(code)
    if product is not None:
        try:
            cart.add(product)
        except InsufficientStock:
            messages.error(request, _("Stok '%(name)s' tidak cukup.") % {"name": product.name})
        else:
            messages.success(request, _("'%(name)s' ditambahkan.") % {"name": product.name})
        return redirect("transaction:make_transaction")
    booking = pos.find_booking(code)
    if booking is not None:
        try:
            cart.add_service(booking)
        except PetshopError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, _("Tagihan booking #%(pk)s ditambahkan.") % {"pk": booking.pk})
        return redirect("transaction:make_transaction")
    messages.error(request, _("Kode '%(code)s' tidak dikenal. Periksa kode barang atau cari dengan nama.") % {"code": code[:40]})
    return redirect("transaction:make_transaction")


@roleRequired(*POS_ROLES)
@require_POST
def add_booking(request):
    booking = pos.find_booking("#" + (request.POST.get("booking") or "").strip())
    if booking is None:
        messages.error(request, _("Pilih booking yang akan dibayar."))
    else:
        try:
            _cart(request.user).add_service(booking)
        except PetshopError as e:
            messages.error(request, str(e))
    return redirect("transaction:make_transaction")


@roleRequired(*POS_ROLES)
@require_POST
def remove_booking(request, pk):
    CartService.objects.filter(pk=pk, cart__user=request.user).delete()
    return redirect("transaction:make_transaction")


@roleRequired(*POS_ROLES)
@require_POST
def submit_transaction(request):
    cart = get_object_or_404(Cart, user=request.user)
    post = request.POST
    customer = None
    if post.get("customer"):
        customer = Customer.objects.filter(pk=post.get("customer")).first()
        if customer is None:
            messages.error(request, _("Pelanggan tidak ditemukan."))
            return redirect("transaction:make_transaction")
    numbers = {k: _int(post.get(k)) for k in ("discount", "shipping_fee", "pay_transfer", "pay_qris", "cash_received")}
    if any(v is None for v in numbers.values()):
        messages.error(request, _("Nominal harus berupa angka."))
        return redirect("transaction:make_transaction")
    courier = User.couriers().filter(pk=post.get("courier") or None).first()
    try:
        order = pos.checkout(
            cart,
            request.user,
            customer=customer,
            buyer_name=post.get("buyer_name", ""),
            buyer_phone=post.get("buyer_phone", ""),
            fulfillment=post.get("fulfillment") or Fulfillment.TAKE_AWAY,
            courier=courier,
            note=post.get("note", ""),
            discount_reason=post.get("discount_reason", ""),
            noncash_confirmed=bool(post.get("noncash_confirmed")),
            pay_on_delivery=bool(post.get("pay_on_delivery")),
            **numbers,
        )
    except PetshopError as e:
        messages.error(request, str(e))
        return redirect("transaction:make_transaction")
    if order.payment_status == PaymentStatus.PAID:
        messages.success(request, _("Transaksi %(no)s lunas.") % {"no": order.receipt_no})
    else:
        messages.success(
            request, _("Pesanan %(no)s disimpan. Kurir menagih tunai saat barang sampai.") % {"no": order.receipt_no}
        )
    return redirect(reverse("transaction:receipt", args=[order.pk]) + "?print=1")


# ---------------------------------------------------------------- beranda kasir


@roleRequired(*POS_ROLES)
def cashier_home(request):
    """Beranda kasir: status shift, pekerjaan yang menunggu, dan struk terakhir."""
    from account import dashboard

    current = CashierShift.current(request.user)
    bookings = dashboard.bookings_today()
    for b in bookings:
        b.tone = dashboard.BOOKING_TONES.get(b.status, "mute")
    tasks = dashboard.staff_tasks(request.user)
    recent = (
        Order.objects.filter(admin=request.user, receipt_no__isnull=False)
        .select_related("customer").prefetch_related("payments").order_by("-date", "-pk")[:6]
    )
    return render(
        request,
        "transaction/cashier_home.html",
        {
            "shift": current,
            "summary": current.summary() if current else None,
            "held_sales": HeldSale.objects.filter(cashier=request.user),
            "tasks": tasks,
            "tasks_total": sum(t["n"] for t in tasks),
            "recent": recent,
            "bookings": bookings,
        },
    )


# ---------------------------------------------------------------- shift


@roleRequired(*POS_ROLES)
def shift(request):
    current = CashierShift.current(request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        amount = _int(request.POST.get("amount"), default=None)
        try:
            if action == "open":
                pos.open_shift(request.user, amount)
                messages.success(request, _("Kasir dibuka. Selamat bekerja!"))
                return redirect("transaction:make_transaction")
            if action == "close" and current:
                current.close(amount, request.POST.get("note", ""))
                messages.success(request, _("Kasir ditutup. Rekap tersimpan."))
                return redirect("transaction:shift")
        except PetshopError as e:
            messages.error(request, str(e))
        return redirect("transaction:shift")
    history = CashierShift.objects.filter(cashier=request.user).exclude(pk=getattr(current, "pk", None))[:14]
    return render(
        request,
        "transaction/shift.html",
        {"current": current, "summary": current.summary() if current else None, "history": history},
    )


# ---------------------------------------------------------------- parkir


@roleRequired(*POS_ROLES)
@require_POST
def hold_sale(request):
    try:
        held = pos.hold(_cart(request.user), request.user, request.POST.get("label", ""))
    except PetshopError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, _("Transaksi diparkir (%(label)s). Layani pembeli berikutnya.") % {"label": held.label or "#" + str(held.pk)})
    return redirect("transaction:make_transaction")


@roleRequired(*POS_ROLES)
@require_POST
def resume_sale(request, pk):
    held = get_object_or_404(HeldSale, pk=pk, cashier=request.user)
    if request.POST.get("action") == "delete":
        held.delete()
        messages.success(request, _("Transaksi parkir dihapus."))
        return redirect("transaction:make_transaction")
    try:
        warnings = pos.resume(held, request.user)
    except PetshopError as e:
        messages.error(request, str(e))
    else:
        for w in warnings:
            messages.warning(request, w)
        messages.success(request, _("Transaksi parkir dilanjutkan."))
    return redirect("transaction:make_transaction")


# ---------------------------------------------------------------- struk


def _receipt_context(request, order):
    public_url = request.build_absolute_uri(reverse("transaction:receipt_public", args=[order.receipt_token]))
    text = _(
        "Struk belanja %(store)s %(no)s, total Rp %(total)s. Lihat struk: %(url)s"
    ) % {
        "store": StoreSettings.current().name, "no": order.receipt_no,
        "total": f"{order.total_payment:,}".replace(",", "."), "url": public_url,
    }
    wa = order.buyer_whatsapp_url or "https://wa.me/"
    return {
        "order": order,
        "store": StoreSettings.current(),
        "details": order.details.select_related("product"),
        "service_lines": order.service_lines.all(),
        "payments": order.payments.all(),
        "public_url": public_url,
        "share_wa_url": f"{wa}?text={urlquote(text)}",
        "returns": order.returns.prefetch_related("lines__detail__product"),
    }


def _handover_share(request, order):
    """Tautan lacak berkunci berisi QR serah-terima, untuk dikirim ke WhatsApp pembeli."""
    link = request.build_absolute_uri(
        reverse("customer:track_detail", args=[order.tracking_number]) + "?k=" + order.handover_key
    )
    cod = order.payment_method == PaymentMethod.CASH and order.payment_status != PaymentStatus.PAID
    text = _(
        "Halo %(name)s, pesanan %(store)s %(no)s akan diantar kurir. Total Rp %(total)s%(cod)s. "
        "Saat paket tiba, buka tautan ini dan tunjukkan QR-nya ke kurir: %(url)s"
    ) % {
        "name": order.buyer_display, "store": StoreSettings.current().name, "no": order.receipt_no,
        "total": f"{order.total_payment:,}".replace(",", "."),
        "cod": _(", dibayar tunai ke kurir") if cod else "", "url": link,
    }
    wa = order.buyer_whatsapp_url
    return {
        "handover_link": link,
        "handover_wa_url": f"{wa}?text={urlquote(text)}" if wa else "",
    }


@roleRequired(*POS_ROLES)
def receipt(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer", "admin", "voided_by"), pk=pk)
    if not order.receipt_no:
        raise Http404("Transaksi ini tidak punya struk.")
    size = "a4" if request.GET.get("size") == "a4" else "58"
    context = _receipt_context(request, order)
    context.update(
        size=size,
        auto_print=request.GET.get("print") == "1",
        can_void=request.user.role in ADMIN_ROLES and order.order_status not in (OrderStatus.CANCELLED, OrderStatus.ON_DELIVERY),
        can_return=pos.can_return(order),
        staff_view=True,
        log=ActivityLog.for_object(order),
    )
    if order.shows_handover_qr:
        context.update(_handover_share(request, order))
    return render(request, "transaction/receipt_staff.html", context)


def receipt_public(request, token):
    order = get_object_or_404(Order.objects.select_related("customer", "admin"), receipt_token=token)
    context = _receipt_context(request, order)
    context.update(size="58", staff_view=False)
    response = render(request, "transaction/receipt.html", context)
    response["X-Robots-Tag"] = "noindex"
    return response


def receipt_qr(request, token):
    order = get_object_or_404(Order, receipt_token=token)
    return qr_response(request.build_absolute_uri(reverse("transaction:receipt_public", args=[order.receipt_token])))


@roleRequired(Role.ADMIN)
@require_POST
def void_transaction(request, pk):
    order = get_object_or_404(Order, pk=pk)
    try:
        pos.void(order, request.user, request.POST.get("reason", ""))
    except PetshopError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, _("Transaksi dibatalkan, stok dikembalikan."))
        if order.payment_status == "LUNAS":
            messages.warning(request, _("Kembalikan uang pembeli sesuai metode bayarnya."))
    if order.receipt_no:
        return redirect("transaction:receipt", pk=order.pk)
    return redirect("transaction:manage_transaction")


# ---------------------------------------------------------------- retur


@roleRequired(*POS_ROLES)
def return_create(request, pk):
    order = get_object_or_404(Order.objects.select_related("customer"), pk=pk)
    details = list(order.details.select_related("product"))
    for d in details:
        d.returnable = pos.returnable_qty(d)
    if request.method == "POST":
        quantities = {d.pk: request.POST.get(f"qty_{d.pk}") or 0 for d in details}
        try:
            pos.request_return(
                order, request.user, quantities, request.POST.get("reason", ""),
                request.POST.get("refund_method") or PaymentMethod.CASH,
            )
        except PetshopError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, _("Retur diajukan. Menunggu persetujuan admin."))
            return redirect("transaction:returns")
    return render(
        request,
        "transaction/return_form.html",
        {
            "order": order, "details": details, "deadline": pos.return_deadline(order),
            "can_return": pos.can_return(order),
            "refund_methods": [(m.value, m.label) for m in COUNTER_PAYMENT_METHODS],
        },
    )


@roleRequired(*POS_ROLES)
def returns(request):
    qs = ReturnRequest.objects.select_related("order", "requested_by", "decided_by").prefetch_related("lines__detail__product")
    status = request.GET.get("status") or ReturnStatus.PENDING
    if status in ReturnStatus.values:
        qs = qs.filter(status=status)
    counts = dict(ReturnRequest.objects.values_list("status").annotate(n=Count("pk")))
    return render(
        request,
        "transaction/returns.html",
        {"items": qs[:100], "status": status, "statuses": ReturnStatus.choices,
         "tabs": [(value, label, counts.get(value, 0)) for value, label in ReturnStatus.choices],
         "return_days": StoreSettings.current().return_days,
         "can_decide": request.user.role in ADMIN_ROLES},
    )


@roleRequired(Role.ADMIN)
@require_POST
def return_decide(request, pk):
    req = get_object_or_404(ReturnRequest, pk=pk)
    approve = request.POST.get("decision") == "approve"
    try:
        pos.decide_return(req, request.user, approve, request.POST.get("note", ""))
    except PetshopError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, _("Retur disetujui, stok dikembalikan.") if approve else _("Retur ditolak."))
    return redirect("transaction:returns")


# ---------------------------------------------------------------- laporan


@roleRequired(Role.ADMIN)
def cashier_report_view(request):
    days = _int(request.GET.get("range"), default=7)
    days = days if days in REPORT_RANGES else 7
    period = Period.last_days(days)
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="laporan-kasir-{days}hari.csv"'
        response.write("﻿")
        writer = csv.writer(response)
        writer.writerow([
            "No. struk", "Tanggal", "Kasir", "Pembeli", "Cara", "Status", "Subtotal", "Diskon",
            "Pajak", "Ongkir", "Total", "Metode", "Rincian bayar", "Tunai diterima", "Kembalian", "Alasan batal",
        ])
        for o in counter_sales(period):
            writer.writerow([
                o.receipt_no, timezone.localtime(o.date).strftime("%Y-%m-%d %H:%M"),
                o.admin.display_name if o.admin else "", o.buyer_display, o.get_fulfillment_display(),
                o.status_display, o.subtotal_before_discount, o.discount, o.tax_amount, o.shipping_fee,
                o.total_payment, o.get_payment_method_display(),
                "; ".join(f"{p.get_method_display()} {p.amount}" for p in o.payments.all()),
                o.cash_received, o.change_given, o.void_reason,
            ])
        return response
    return render(
        request,
        "transaction/cashier_report.html",
        {"report": cashier_report(period), "period": period, "range": days, "ranges": REPORT_RANGES,
         "sales": counter_sales(period)[:50]},
    )


# ---------------------------------------------------------------- label kode barang


@roleRequired(Role.ADMIN)
def product_codes(request):
    if request.method == "POST":
        made = pos.assign_codes()
        messages.success(request, _("%(n)s produk diberi kode otomatis.") % {"n": made})
        return redirect("transaction:product_codes")
    products = Product.objects.filter(is_active=True).order_by("category__name", "name")
    return render(
        request,
        "transaction/product_codes.html",
        {"products": products, "missing": Product.objects.filter(sku__isnull=True).count()},
    )


@roleRequired(*POS_ROLES)
def product_code_qr(request, pk):
    product = get_object_or_404(Product, pk=pk, sku__isnull=False)
    return qr_response(product.sku)
