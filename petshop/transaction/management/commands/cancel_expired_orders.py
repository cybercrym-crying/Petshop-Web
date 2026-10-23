from django.core.management.base import BaseCommand

from transaction.models import Order


class Command(BaseCommand):
    help = "Batalkan pesanan transfer yang lewat batas bayar tanpa bukti (bisa dijadwalkan lewat cron)."

    def handle(self, *args, **options):
        count = Order.cancel_expired()
        self.stdout.write(f"{count} pesanan dibatalkan.")
