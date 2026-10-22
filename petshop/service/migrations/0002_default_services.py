"""Isi awal daftar jasa supaya halaman layanan langsung bisa dipakai.
Harga & nama bisa diubah admin di menu Jenis Layanan."""

from django.db import migrations

DEFAULT_SERVICES = [
    ("Mandi Sehat Kucing", "Mandi dengan sampo khusus, keringkan, sisir bulu.", 60000, 60, "KUCING"),
    ("Grooming Lengkap Kucing", "Mandi, potong kuku, bersihkan telinga, rapikan bulu.", 120000, 90, "KUCING"),
    ("Mandi Sehat Anjing", "Mandi dengan sampo khusus, keringkan, sisir bulu.", 80000, 60, "ANJING"),
    ("Grooming Lengkap Anjing", "Mandi, potong kuku, bersihkan telinga, potong & rapikan bulu.", 150000, 120, "ANJING"),
    ("Potong Kuku", "Potong dan haluskan kuku hewan.", 25000, 15, "SEMUA"),
    ("Mandi Kutu & Jamur", "Mandi dengan sampo anti kutu/jamur sesuai kondisi kulit.", 100000, 75, "SEMUA"),
]


def add_services(apps, schema_editor):
    Service = apps.get_model("service", "Service")
    for name, description, price, minutes, pet in DEFAULT_SERVICES:
        Service.objects.get_or_create(
            name=name,
            defaults={
                "description": description,
                "price": price,
                "duration_minutes": minutes,
                "pet_type": pet,
            },
        )


def remove_services(apps, schema_editor):
    Service = apps.get_model("service", "Service")
    Service.objects.filter(
        name__in=[s[0] for s in DEFAULT_SERVICES], bookings__isnull=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("service", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_services, remove_services),
    ]
