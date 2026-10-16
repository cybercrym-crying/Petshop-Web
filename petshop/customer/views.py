from django.shortcuts import render
from product.models import Product
from account.models import Customer
from transaction.models import Order, OrderStatus

ADMIN_WA_NUMBER = "6281356703075"
WA_LINK = f"https://wa.me/{ADMIN_WA_NUMBER}"
WA_DISPLAY = "+62 813-5670-3075"

# untuk promom di halaman
SPECIAL_OFFER = {
    "title": "Get 20% OFF on Selected Pet Products",
    "text": "Premium brands, your pet's favorite items, at a special price!",
}
STORE_ADDRESS = "Samarinda, Jl Jakarta Gg 19B"


def _site_context(**extra):
    return {"wa_link": WA_LINK, "wa_display": WA_DISPLAY, **extra}


def home(request):
    return render(request, "customer/home.html", _site_context(offer=SPECIAL_OFFER))


def about(request):
    stats = {
        "products": Product.objects.sellable().count(),
        "orders": Order.objects.filter(order_status=OrderStatus.DELIVERED).count(),
        "customers": Customer.objects.count(),
    }
    return render(
        request,
        "customer/about.html",
        _site_context(stats=stats, store_address=STORE_ADDRESS),
    )


def cart_page(request):
    return render(request, "customer/cart.html")


def katalog_publik(request):
    produk_tersedia = (
        Product.objects.sellable().select_related("category").order_by("name")
    )

    return render(
        request, "customer/catalog.html", _site_context(produk=produk_tersedia)
    )


def checkout_page(request):
    return render(request, "customer/checkout.html")
