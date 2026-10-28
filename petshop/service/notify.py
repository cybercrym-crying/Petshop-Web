"""Riwayat status + notifikasi pelanggan untuk booking layanan (satu tempat, dipanggil dari view)."""

from django.urls import reverse

from store.models import ActivityLog, Notification


def booking_event(booking, action, actor=None, customer_title=None, customer_body="", detail="",
                  photo=None, lat=None, lng=None):
    ActivityLog.record(booking, action, actor=actor, detail=detail, photo=photo, lat=lat, lng=lng)
    if customer_title and booking.customer_id and not booking.is_guest:
        Notification.send(
            booking.customer, customer_title, customer_body,
            reverse("service:my_bookings") + f"#booking-{booking.pk}",
        )
