from django.shortcuts import render, redirect
from product.models import Product
from account.models import Customer
from transaction.models import Order, OrderStatus
import urllib.parse
import json


# Nomor WhatsApp admin (format internasional tanpa +), dipakai tombol kontak dan pesanan.
ADMIN_WA_NUMBER = "6281356703075"
WA_LINK = f"https://wa.me/{ADMIN_WA_NUMBER}"
WA_DISPLAY = "+62 813-5670-3075"


# Banner promo di Home. Isi dengan promo yang benar-benar berlaku, atau ubah jadi None
# untuk menyembunyikannya (banner "Ready to Order" akan tampil sebagai gantinya).
SPECIAL_OFFER = {
    "title": "Get 20% OFF on Selected Pet Products",
    "text": "Premium brands, your pet's favorite items, at a special price!",
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


def katalog_publik(request):
    produk_tersedia = (
        Product.objects.sellable().select_related("category").order_by("name")
    )

    return render(
        request, "customer/catalog.html", _site_context(produk=produk_tersedia)
    )


def form_pemesanan_publik(request):
    if request.method == "POST":
        nama_customer = request.POST.get("nama")
        no_wa_customer = request.POST.get("no_wa")
        alamat = request.POST.get("alamat")
        catatan = request.POST.get("catatan", "-")

        Customer.objects.get_or_create(
            phone_number=no_wa_customer,
            defaults={"name": nama_customer, "address": alamat},
        )

        cart_data = request.POST.get("cart_data", "")

        nomor_admin = ADMIN_WA_NUMBER

        pesan = (
            f"Halo Kak, mau order barang dong\n\n"
            f"*Format Pemesanan*\n"
            f"• Nama Lengkap: {nama_customer}\n"
            f"• No. HP/WA: {no_wa_customer}\n"
            f"• Alamat Lengkap: {alamat}\n\n"
            f"*Order Summary:*\n"
        )

        if cart_data:
            try:
                cart_items = json.loads(cart_data)
                for item in cart_items:
                    harga = int(item["price"])
                    harga_str = f"Rp {harga:,}".replace(",", ".")
                    pesan += f"- {item['name']} - {item['quantity']}x ({harga_str})\n"
            except json.JSONDecodeError:
                pesan += "- Data keranjang tidak valid\n"
        else:
            # Fallback untuk pesanan manual
            nama_produk = request.POST.get("nama_produk", "Produk")
            jumlah = request.POST.get("jumlah", "1")
            pesan += f"- {nama_produk} - {jumlah}x\n"

        pesan += f"\n*Catatan:* {catatan}\n\nMohon info total biaya + ongkirnya ya kak. Terima kasih!"

        # Redirect ke WhatsApp
        pesan_encoded = urllib.parse.quote(pesan)
        url_wa = f"https://wa.me/{nomor_admin}?text={pesan_encoded}"

        return redirect(url_wa)

    return render(request, "customer/order_form.html")


def checkout_page(request):
    return render(request, "customer/checkout.html")
