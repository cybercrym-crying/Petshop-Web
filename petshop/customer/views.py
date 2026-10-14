from django.shortcuts import render, redirect
from product.models import Product
from account.models import Customer
import urllib.parse
import json


def cart_page(request):
    return render(request, "customer/cart.html")


def katalog_publik(request):
    produk_tersedia = (
        Product.objects.sellable().select_related("category").order_by("name")
    )

    return render(request, "customer/catalog.html", {"produk": produk_tersedia})


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

        nomor_admin = "6281356703075"

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
