import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

PET_TYPES = [
    ("SEMUA", "Semua hewan"),
    ("KUCING", "Kucing"),
    ("ANJING", "Anjing"),
    ("BURUNG", "Burung"),
    ("KELINCI", "Kelinci"),
    ("IKAN", "Ikan"),
    ("HAMSTER", "Hamster"),
]


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("account", "0008_delete_customer_table"),
    ]

    operations = [
        migrations.CreateModel(
            name="Service",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120, unique=True, verbose_name="Nama layanan")),
                ("description", models.TextField(blank=True, default="", verbose_name="Deskripsi")),
                ("price", models.PositiveBigIntegerField(verbose_name="Harga")),
                ("duration_minutes", models.PositiveIntegerField(default=60, verbose_name="Durasi (menit)")),
                ("pet_type", models.CharField(choices=PET_TYPES, default="SEMUA", max_length=20, verbose_name="Untuk hewan")),
                ("is_active", models.BooleanField(default=True, verbose_name="Aktif")),
            ],
            options={
                "verbose_name": "layanan",
                "verbose_name_plural": "layanan",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ServiceBooking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("pet_name", models.CharField(max_length=60, verbose_name="Nama hewan")),
                ("pet_type", models.CharField(choices=PET_TYPES, max_length=20, verbose_name="Jenis hewan")),
                ("schedule", models.DateTimeField(verbose_name="Jadwal")),
                ("customer_note", models.CharField(blank=True, default="", max_length=255, verbose_name="Catatan pelanggan")),
                ("price", models.PositiveBigIntegerField(verbose_name="Harga")),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("PROSES", "Proses"), ("SELESAI", "Selesai")], db_index=True, default="PENDING", max_length=10)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("groomer_note", models.CharField(blank=True, default="", max_length=255, verbose_name="Catatan groomer")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(limit_choices_to={"role": "CUSTOMER"}, on_delete=django.db.models.deletion.PROTECT, related_name="service_bookings", to=settings.AUTH_USER_MODEL)),
                ("groomer", models.ForeignKey(blank=True, limit_choices_to={"role": "GROOMER"}, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="grooming_jobs", to=settings.AUTH_USER_MODEL)),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bookings", to="service.service")),
            ],
            options={
                "verbose_name": "booking layanan",
                "verbose_name_plural": "booking layanan",
                "ordering": ["schedule", "pk"],
            },
        ),
    ]
