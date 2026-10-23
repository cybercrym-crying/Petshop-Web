"""Tahapan kerja bawaan untuk layanan bawaan (admin bisa mengubahnya di Jenis Layanan → Tahapan)."""

from django.db import migrations

STEPS = {
    "Mandi Sehat Kucing": [("Pemeriksaan awal kulit & bulu", True), ("Mandi sampo", True), ("Pengeringan", False), ("Sisir & finishing", True)],
    "Mandi Sehat Anjing": [("Pemeriksaan awal kulit & bulu", True), ("Mandi sampo", True), ("Pengeringan", False), ("Sisir & finishing", True)],
    "Grooming Lengkap Kucing": [
        ("Pemeriksaan awal", True), ("Potong kuku & bersihkan telinga", True), ("Mandi", True),
        ("Pengeringan", False), ("Rapikan bulu", True), ("Finishing & pemeriksaan akhir", True),
    ],
    "Grooming Lengkap Anjing": [
        ("Pemeriksaan awal", True), ("Potong kuku & bersihkan telinga", True), ("Mandi", True),
        ("Pengeringan", False), ("Potong & rapikan bulu", True), ("Finishing & pemeriksaan akhir", True),
    ],
    "Potong Kuku": [("Pemeriksaan kuku", True), ("Potong & haluskan kuku", True)],
    "Mandi Kutu & Jamur": [
        ("Pemeriksaan kulit (kutu/jamur)", True), ("Mandi sampo anti kutu/jamur", True),
        ("Pembilasan & pengeringan", False), ("Pemeriksaan akhir", True),
    ],
}


def forwards(apps, schema_editor):
    Service = apps.get_model("service", "Service")
    ServiceStep = apps.get_model("service", "ServiceStep")
    for name, steps in STEPS.items():
        service = Service.objects.filter(name=name).first()
        if service is None or ServiceStep.objects.filter(service=service).exists():
            continue
        ServiceStep.objects.bulk_create(
            ServiceStep(service=service, position=n, name=step, needs_photo=photo)
            for n, (step, photo) in enumerate(steps, start=1)
        )


class Migration(migrations.Migration):
    dependencies = [("service", "0004_servicestep_servicebooking_checked_in_at_and_more")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
