"""Tambah role CUSTOMER, KASIR, GROOMER + kolom alamat di User, lalu salin
semua baris tabel account_customer menjadi User ber-role CUSTOMER.

Tabel account_customer sendiri baru dihapus di 0008, setelah Order.customer
dipindah ke User (transaction 0008)."""

import re

from django.contrib.auth.hashers import make_password
from django.db import migrations, models


def _username_base(raw):
    cleaned = re.sub(r"[^\w.@+-]", "", raw or "")
    return (cleaned or "pelanggan")[:140]


def customers_to_users(apps, schema_editor):
    Customer = apps.get_model("account", "Customer")
    User = apps.get_model("account", "User")
    for customer in Customer.objects.order_by("pk"):
        if User.objects.filter(
            role="CUSTOMER", phone_number=customer.phone_number
        ).exists():
            continue
        base = _username_base(customer.phone_number)
        username, n = base, 2
        while User.objects.filter(username__iexact=username).exists():
            username = f"{base}-{n}"
            n += 1
        first, _, last = (customer.name or "").strip().partition(" ")
        User.objects.create(
            username=username,
            first_name=first[:150],
            last_name=last.strip()[:150],
            phone_number=customer.phone_number,
            address=customer.address,
            role="CUSTOMER",
            # Belum bisa login sampai admin/pelanggan memberi kata sandi.
            password=make_password(None),
        )


def users_to_customers(apps, schema_editor):
    Customer = apps.get_model("account", "Customer")
    User = apps.get_model("account", "User")
    for user in User.objects.filter(role="CUSTOMER"):
        name = f"{user.first_name} {user.last_name}".strip() or user.username
        Customer.objects.get_or_create(
            phone_number=user.phone_number,
            defaults={"name": name, "address": user.address or "-"},
        )
    User.objects.filter(role="CUSTOMER").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0006_nilai_bahasa_indonesia"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="address",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Admin"),
                    ("KURIR", "Kurir"),
                    ("KASIR", "Kasir"),
                    ("GROOMER", "Groomer"),
                    ("CUSTOMER", "Customer"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(customers_to_users, users_to_customers),
    ]
