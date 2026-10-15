from datetime import timedelta

from account.decorators import roleRequired
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from product.models import Product, InsufficientStock
from account.models import Customer, User, Role
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
    (OrderStatus.CONFIRMED, "confirmed", "Confirmed"),
    (OrderStatus.ON_DELIVERY, "on-delivery", "On delivery"),
    (OrderStatus.DELIVERED, "delivered", "Delivered"),
    (OrderStatus.CANCELLED, "cancelled", "Cancelled"),
)
OPEN_STATUSES = (OrderStatus.CONFIRMED, OrderStatus.ON_DELIVERY)
CLOSED_COLUMN_LIMIT = 12
UNPAID_GRACE = timedelta(hours=1)


def _resolve_customer(post):
    """Customer dipilih dari dropdown; customer baru ditambah lewat Manage Account."""
    customer = Customer.objects.filter(pk=post.get("customer") or None).first()
    if customer is None:
        raise CheckoutError("Pilih customer terlebih dahulu.")
    return customer


def _get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


@roleRequired(Role.ADMIN)
def make_transaction(request):
    cart = _get_or_create_cart(request.user)
    products = Product.objects.sellable()
    q = request.GET.get("q")
    if q:
        products = products.filter(name__icontains=q)

    cart_items = cart.items.select_related("product")
    cart_total = cart.total

    return render(
        request,
        "transaction/make_transaction.html",
        {
            "products": products,
            "cart_items": cart_items,
            "cart_total": cart_total,
            "customers": Customer.objects.all(),
            "couriers": User.objects.filter(role=Role.COURIER),
        },
    )


@roleRequired(Role.ADMIN)
def add_to_cart(request, pk):
    if request.method == "POST":
        product = get_object_or_404(Product, pk=pk)
        cart = _get_or_create_cart(request.user)
        if product.stock <= 0:
            messages.error(request, f"Stok '{product.name}' habis.")
        else:
            item, created = CartItem.objects.get_or_create(cart=cart, product=product)
            if not created:
                item.quantity = F("quantity") + 1
                item.save(update_fields=["quantity"])
            messages.success(request, f"'{product.name}' ditambahkan.")
    return redirect("transaction:make_transaction")


@roleRequired(Role.ADMIN)
def remove_from_cart(request, pk):
    if request.method == "POST":
        item = get_object_or_404(CartItem, pk=pk, cart__user=request.user)
        item.delete()
    return redirect("transaction:make_transaction")


@roleRequired(Role.ADMIN)
def update_cart_quantity(request, pk):
    if request.method == "POST":
        cart = get_object_or_404(Cart, user=request.user)
        try:
            quantity = int(request.POST.get("quantity", ""))
        except ValueError:
            messages.error(request, "Jumlah harus berupa angka.")
            return redirect("transaction:make_transaction")
        try:
            cart.set_quantity(get_object_or_404(cart.items, pk=pk).pk, quantity)
        except InsufficientStock as e:
            messages.error(request, str(e))
    return redirect("transaction:make_transaction")


@roleRequired(Role.ADMIN)
def cancel_transaction(request):
    if request.method == "POST":
        Cart.objects.filter(user=request.user).delete()
        messages.success(request, "Transaksi dibatalkan.")
    return redirect("transaction:make_transaction")


@roleRequired(Role.ADMIN)
def submit_transaction(request):
    if request.method == "POST":
        cart = get_object_or_404(Cart, user=request.user)

        try:
            customer = _resolve_customer(request.POST)
        except CheckoutError as e:
            messages.error(request, str(e))
            return redirect("transaction:make_transaction")

        paymentMethod = request.POST.get("payment_method")
        if paymentMethod not in PaymentMethod.values:
            messages.error(request, "Metode pembayaran tidak valid.")
            return redirect("transaction:make_transaction")

        courier = User.objects.filter(
            pk=request.POST.get("courier") or None, role=Role.COURIER
        ).first()

        try:
            cart.checkout(
                customer=customer,
                admin=request.user,
                payment_method=paymentMethod,
                courier=courier,
            )
        except (CheckoutError, InsufficientStock) as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "Transaksi berhasil dibuat.")
    return redirect("transaction:make_transaction")


@roleRequired(Role.ADMIN)
def manage_transaction(request):
    view = "list" if request.GET.get("view") == "list" else "board"
    q = request.GET.get("q", "").strip()
    only_unpaid = request.GET.get("payment") == "pending"

    orders = (
        Order.objects.select_related("customer", "admin", "courier")
        .prefetch_related("details__product")
        .order_by("-date")
    )
    if q:
        cond = Q(customer__name__icontains=q)
        digits = q.lstrip("#")
        if digits.isdigit() and len(digits) <= 9:
            cond |= Q(pk=int(digits))
        orders = orders.filter(cond)
    if only_unpaid:
        orders = orders.filter(payment_status=PaymentStatus.PENDING).exclude(
            order_status=OrderStatus.CANCELLED
        )

    cutoff = timezone.now() - UNPAID_GRACE

    def flag_overdue(order):
        # Transfer yang belum dibayar lewat 1 jam. CASH dibayar saat diantar,
        # jadi belum lunas di awal itu normal dan tidak ditandai.
        order.overdue = (
            order.payment_status == PaymentStatus.PENDING
            and order.payment_method == PaymentMethod.TRANSFER
            and order.order_status != OrderStatus.CANCELLED
            and order.date < cutoff
        )
        return order

    columns = []
    if view == "board":
        for status, css, title in BOARD_COLUMNS:
            qs = orders.filter(order_status=status)
            count = qs.count()
            is_open = status in OPEN_STATUSES
            shown = [flag_overdue(o) for o in (qs if is_open else qs[:CLOSED_COLUMN_LIMIT])]
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
        transactions = [o for col in columns for o in col["orders"]]
    else:
        transactions = [flag_overdue(o) for o in orders]

    active = Order.objects.filter(order_status__in=OPEN_STATUSES).aggregate(
        n=Count("pk"), total=Sum("total_payment")
    )
    overdue_unpaid = (
        Order.objects.filter(
            payment_status=PaymentStatus.PENDING,
            payment_method=PaymentMethod.TRANSFER,
            date__lt=cutoff,
        )
        .exclude(order_status=OrderStatus.CANCELLED)
        .count()
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
            "couriers": User.objects.filter(role=Role.COURIER),
        },
    )


@roleRequired(Role.ADMIN)
def update_status(request, pk):
    if request.method != "POST":
        return redirect("transaction:manage_transaction")

    action = request.POST.get("action")
    try:
        with transaction.atomic():
            order = get_object_or_404(Order.objects.select_for_update(), pk=pk)
            if action == "paid":
                order.mark_paid()
                messages.success(request, f"Order #{order.pk} ditandai lunas.")
            elif action == "on_delivery":
                courier = User.objects.filter(
                    pk=request.POST.get("courier") or None, role=Role.COURIER
                ).first()
                order.mark_on_delivery(courier)
                messages.success(request, f"Order #{order.pk} sedang dikirim.")
            elif action == "delivered":
                order.mark_delivered()
                messages.success(request, f"Order #{order.pk} selesai diantar.")
            elif action == "cancel":
                order.cancel()
                messages.success(
                    request, f"Order #{order.pk} dibatalkan, stok dikembalikan."
                )
                if order.payment_status == PaymentStatus.PAID:
                    messages.warning(
                        request, "Order sudah lunas: kembalikan dana ke customer."
                    )
            else:
                messages.error(request, "Aksi tidak dikenal.")
    except InvalidTransition as e:
        messages.error(request, str(e))
    return redirect("transaction:manage_transaction")
