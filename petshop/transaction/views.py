from account.decorators import roleRequired
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import F
from product.models import Product, InsufficientStock
from account.models import Customer, User, Role
from .models import (
    Cart,
    CartItem,
    CheckoutError,
    InvalidTransition,
    Order,
    PaymentMethod,
    PaymentStatus,
)


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
    transactions = (
        Order.objects.select_related("customer", "admin", "courier")
        .prefetch_related("details__product")
        .order_by("-date")
    )
    return render(
        request,
        "transaction/manage_transaction.html",
        {
            "transactions": transactions,
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
