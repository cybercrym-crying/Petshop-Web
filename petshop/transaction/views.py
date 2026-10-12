from account.decorators import roleRequired
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import F
from product.models import Product, InsufficientStock
from account.models import Customer, User, Role
from .models import Cart, CartItem, CheckoutError, PaymentMethod


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
            "couriers": User.objects.filter(role=Role.COURIR),
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

        customer = Customer.objects.filter(pk=request.POST.get("customer") or None).first()
        if customer is None:
            messages.error(request, "Pilih customer terlebih dahulu.")
            return redirect("transaction:make_transaction")

        paymentMethod = request.POST.get("payment_method")
        if paymentMethod not in PaymentMethod.values:
            messages.error(request, "Metode pembayaran tidak valid.")
            return redirect("transaction:make_transaction")

        courier = User.objects.filter(
            pk=request.POST.get("courier") or None, role=Role.COURIR
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
    if request.method == "POST":
        pass
    return render(request, "transaction/manage_transaction.html")


# Create your views here.
