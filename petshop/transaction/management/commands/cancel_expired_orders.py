from django.core.management.base import BaseCommand

from service.models import ServiceBooking
from transaction.models import Order


class Command(BaseCommand):
    help = "Batalkan pesanan & booking transfer/QRIS yang lewat batas bayar tanpa bukti (jadwalkan lewat cron)."

    def handle(self, *args, **options):
        orders = Order.cancel_expired()
        bookings = ServiceBooking.cancel_expired()
        self.stdout.write(f"{orders} pesanan dan {bookings} booking dibatalkan.")
