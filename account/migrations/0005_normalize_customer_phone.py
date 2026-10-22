import re

from django.db import migrations


def _normalize(raw):
    cleaned = re.sub(r"[\s().-]", "", raw or "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not cleaned.isdigit():
        return None
    if cleaned.startswith("62"):
        cleaned = "0" + cleaned[2:]
    elif cleaned.startswith("8"):
        cleaned = "0" + cleaned
    if not cleaned.startswith("0") or not 9 <= len(cleaned) <= 14:
        return None
    return cleaned


def normalize_phones(apps, schema_editor):
    Customer = apps.get_model("account", "Customer")
    taken = set(Customer.objects.values_list("phone_number", flat=True))
    for customer in Customer.objects.all():
        new = _normalize(customer.phone_number)
        # nomor tidak valid atau bentrok dengan customer lain dibiarkan apa adanya
        if new and new != customer.phone_number and new not in taken:
            taken.discard(customer.phone_number)
            taken.add(new)
            customer.phone_number = new
            customer.save(update_fields=["phone_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0004_courier_role_unique_phone"),
    ]

    operations = [
        migrations.RunPython(normalize_phones, migrations.RunPython.noop),
    ]
