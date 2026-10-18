from django.shortcuts import get_object_or_404, render
from product.models import Product
from account.models import Customer
from transaction.models import Order, OrderStatus

from .templatetags.customer_extras import KATEGORI

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


# Kategori di halaman Belanja: kode (sama dengan Category.name di database) -> gambar.
CATEGORY_IMAGES = {
    "FOOD": "customer/img/pet-food.png",
    "EQUIPMENT": "customer/img/pet-toys.png",
    "ACCESSORIES": "customer/img/pet-accessories.png",
}
DEFAULT_CATEGORY_IMAGE = "customer/img/product-placeholder.svg"
POPULAR_LIMIT = 8


def _category_cards(products):
    counts = {}
    for product in products:
        code = str(product.category.name).upper()
        counts[code] = counts.get(code, 0) + 1
    # Urutan tetap untuk kategori utama, kategori lain menyusul.
    codes = [c for c in CATEGORY_IMAGES if c in counts]
    codes += sorted(c for c in counts if c not in CATEGORY_IMAGES)
    return [
        {
            "code": code,
            "label": KATEGORI.get(code, code.title()),
            "image": CATEGORY_IMAGES.get(code, DEFAULT_CATEGORY_IMAGE),
            "count": counts[code],
        }
        for code in codes
    ]


def shop(request):
    """Home Shop: hero, kategori, produk populer. Dengan ?q=, ?category= atau
    ?wishlist=1 halaman yang sama menampilkan daftar produk hasil filter."""
    produk = list(
        Product.objects.sellable().select_related("category").order_by("name")
    )
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip().upper()
    wishlist = request.GET.get("wishlist") == "1"

    results = None
    results_title = ""
    if wishlist:
        # Server mengirim semua produk, browser menyembunyikan yang belum difavoritkan.
        results, results_title = produk, "Produk Favorit"
    elif query or category:
        results = produk
        if category:
            results = [p for p in results if str(p.category.name).upper() == category]
            results_title = KATEGORI.get(category, category.title())
        if query:
            results = [p for p in results if query.lower() in p.name.lower()]
            results_title = f"Hasil pencarian “{query}”"

    return render(
        request,
        "customer/home_shop.html",
        _site_context(
            active_page="shop",
            query=query,
            categories=_category_cards(produk),
            popular_products=produk[:POPULAR_LIMIT],
            results=results,
            results_title=results_title,
            wishlist_mode=wishlist,
        ),
    )


def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.sellable().select_related("category"), pk=pk
    )
    related = (
        Product.objects.sellable()
        .select_related("category")
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .order_by("name")[:4]
    )
    return render(
        request,
        "customer/product_detail.html",
        _site_context(active_page="shop", product=product, related_products=related),
    )


def checkout_page(request):
    return render(request, "customer/checkout.html")
