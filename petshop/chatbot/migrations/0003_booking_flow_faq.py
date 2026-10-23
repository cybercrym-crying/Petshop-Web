"""Perbarui jawaban FAQ booking ke alur bertahap (hanya bila admin belum mengubahnya)."""

from django.db import migrations

OLD = (
    "Buka menu Layanan, pilih layanan, isi nama & jenis hewan serta jadwal datang, lalu tekan Buat Booking (perlu akun customer). "
    "Status booking bisa dipantau: Pending → Proses → Selesai."
)
NEW = (
    "Buka menu Layanan, pilih layanan dan hewan Anda, tentukan jadwal (bisa minta dijemput & diantar pulang), lalu tekan Buat Booking "
    "(perlu akun customer). Setelah dikonfirmasi toko, tunjukkan QR booking saat check-in untuk mendapat nomor antrean. "
    "Setiap tahap pengerjaan beserta fotonya bisa dipantau di Booking Saya."
)


def forwards(apps, schema_editor):
    apps.get_model("chatbot", "FaqEntry").objects.filter(answer=OLD).update(answer=NEW)


def backwards(apps, schema_editor):
    apps.get_model("chatbot", "FaqEntry").objects.filter(answer=NEW).update(answer=OLD)


class Migration(migrations.Migration):
    dependencies = [("chatbot", "0002_default_faq")]

    operations = [migrations.RunPython(forwards, backwards)]
