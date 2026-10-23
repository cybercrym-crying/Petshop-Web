"""Kirim notifikasi "waktunya grooming lagi" untuk hewan yang perawatan terakhirnya sudah lewat
N hari (Pengaturan Toko). Jalankan harian lewat cron / Task Scheduler:

    python manage.py send_grooming_reminders
"""

from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from service.models import Pet
from store.models import Notification, StoreSettings


class Command(BaseCommand):
    help = "Ingatkan pelanggan untuk booking grooming lagi (satu kali per perawatan terakhir)."

    def handle(self, *args, **opts):
        days = StoreSettings.current().grooming_reminder_days
        sent = 0
        for pet in Pet.objects.filter(is_active=True, owner__is_active=True).select_related("owner"):
            if not pet.grooming_due(days):
                continue
            last = pet.last_service()
            if pet.reminded_at and last and pet.reminded_at >= last.finished_at:
                continue  # sudah diingatkan untuk perawatan terakhir ini
            Notification.send(
                pet.owner,
                f"Waktunya {pet.name} grooming lagi",
                f"Terakhir {last.service.name} pada {timezone.localtime(last.finished_at):%d %b %Y}.",
                reverse("service:catalog") + f"?hewan={pet.pk}#booking",
            )
            pet.reminded_at = timezone.now()
            pet.save(update_fields=["reminded_at"])
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"{sent} pengingat grooming dikirim."))
