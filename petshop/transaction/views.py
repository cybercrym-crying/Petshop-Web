from account.decorators import roleRequired
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import F
from product.models import Product
from account.models import Customer, User, Role
from .models import Cart, CartItem


def _get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


@roleRequired(Role.ADMIN)
def make_transaction(request):
    cart = _get_or_create_cart(request.user)
    products = Product.objects.filter(is_active=True, selling_price__isnull=False)
    q = request.GET.get("q")
    if q:
        products = products.filter(name__icontains=q)

    cart_items = cart.items.select_related("product")
    cart_total = sum(item.subtotal for item in cart_items)

    return render(
        request,
        "transaction/make_transaction.html",
        {
            "products": products,
            "cart_items": cart_items,
            "cart_total": cart_total,
            "customers": Customer.objects.all(),
            "couriers": User.objects.filter(role=Role.KURIR),
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
def cancel_transaction(request):
    if request.method == "POST":
        Cart.objects.filter(user=request.user).delete()
        messages.success(request, "Transaksi dibatalkan.")
    return redirect("transaction:make_transaction")


@roleRequired(Role.ADMIN)
def submit_transaction(request):
    if request.method == "POST":
        cart = get_object_or_404(Cart, user=request.user)
        items = list(cart.items.select_related("product"))
        if not items:
            messages.error(request, "Belum ada item di order.")
            return redirect("transaction:make_transaction")

        customer_id = request.POST.get("customer")
        if not customer_id:
            messages.error(request, "Pilih customer terlebih dahulu.")
            return redirect("transaction:make_transaction")

        with transaction.atomic():
            for item in items:
                if item.quantity > item.product.stock:
                    messages.error(request, f"Stok '{item.product.name}' tidak cukup.")
                    return redirect("transaction:make_transaction")
                item.product.stock -= item.quantity
                item.product.save(update_fields=["stock"])
            cart.delete()

        messages.success(request, "Transaksi berhasil dibuat.")
    return redirect("transaction:make_transaction")


# Create your views here.
