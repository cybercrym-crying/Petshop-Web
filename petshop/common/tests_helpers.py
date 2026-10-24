"""Alat bantu tes bersama (bukan modul tes, jadi tidak dijalankan test runner)."""

import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def tiny_photo(name="foto.jpg", color="#8c73c2"):
    """Foto JPEG kecil yang lolos validasi clean_photo (format gambar asli)."""
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), color).save(buf, "JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


def pay_booking_at_counter(booking, cashier):
    """Catat booking sebagai dibayar tunai di kasir (sama seperti transaksi kasir berisi layanan)."""
    from transaction.models import (
        Fulfillment, Order, OrderChannel, OrderPayment, OrderServiceLine, OrderStatus,
        PaymentMethod, PaymentStatus,
    )

    order = Order.objects.create(
        admin=cashier, customer=booking.customer, channel=OrderChannel.STORE,
        fulfillment=Fulfillment.TAKE_AWAY, order_status=OrderStatus.DELIVERED,
        payment_method=PaymentMethod.CASH, payment_status=PaymentStatus.PAID,
        total_payment=booking.total_price,
    )
    OrderServiceLine.objects.create(order=order, booking=booking, description="Layanan", amount=booking.total_price)
    OrderPayment.objects.create(order=order, method=PaymentMethod.CASH, amount=booking.total_price)
    return order
