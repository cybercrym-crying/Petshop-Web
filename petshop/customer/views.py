from django.shortcuts import render
from product.models import Product
from account.models import Customer
from transaction.models import Order, OrderStatus

# Nomor WhatsApp admin (format internasional tanpa +), dipakai tombol kontak dan pesanan.
ADMIN_WA_NUMBER = "6281356703075"
WA_LINK = f"https://wa.me/{ADMIN_WA_NUMBER}"
WA_DISPLAY = "+62 813-5670-3075"


# Banner promo di Home. Isi dengan promo yang benar-benar berlaku, atau ubah jadi None
# untuk menyembunyikannya (banner "Ready to Order" akan tampil sebagai gantinya).
SPECIAL_OFFER = {
    "title": "Diskon 20% untuk Produk Pilihan",
    "text": "Merek premium, barang favorit hewan kesayangan Anda, dengan harga spesial!",
}
# Alamat toko di bagian "Visit Us" halaman About. Kosongkan untuk menyembunyikannya.
STORE_ADDRESS = ""


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


def shop(request):
    produk_tersedia = (
        Product.objects.sellable().select_related("category").order_by("name")
    )

    return render(
        request, "customer/catalog.html", _site_context(produk=produk_tersedia)
    )


def checkout_page(request):
    return render(request, "customer/checkout.html")
