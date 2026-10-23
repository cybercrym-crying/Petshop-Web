"""Notifikasi + riwayat status untuk perubahan order (satu tempat, dipanggil dari view)."""

from django.urls import reverse

from store.models import ActivityLog, Notification


def order_event(order, action, actor=None, customer_title=None, customer_body="", detail="",
                photo=None, lat=None, lng=None):
    """Catat riwayat status order; bila customer_title diisi, kirim juga notifikasi ke pelanggan."""
    ActivityLog.record(order, action, actor=actor, detail=detail, photo=photo, lat=lat, lng=lng)
    # "Pelanggan umum" (pembeli kasir tanpa akun) tidak punya kotak notifikasi.
    if customer_title and order.customer_id and not order.customer.is_walk_in:
        Notification.send(
            order.customer,
            customer_title,
            customer_body,
            reverse("customer:track_detail", args=[order.tracking_number]),
        )
