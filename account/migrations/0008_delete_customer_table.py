"""Hapus tabel account_customer. Nama Customer tetap ada sebagai proxy model
di atas User (role=CUSTOMER) tanpa tabel sendiri."""

import account.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0007_user_address_role_customer_kasir_groomer"),
        ("transaction", "0008_order_customer_to_user"),
    ]

    operations = [
        migrations.DeleteModel(name="Customer"),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("role", "CUSTOMER")),
                fields=("phone_number",),
                name="unique_customer_phone",
                violation_error_message="Nomor telepon sudah dipakai pelanggan lain.",
            ),
        ),
        migrations.CreateModel(
            name="Customer",
            fields=[],
            options={
                "verbose_name": "pelanggan",
                "verbose_name_plural": "pelanggan",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("account.user",),
            managers=[
                ("objects", account.models.CustomerManager()),
            ],
        ),
    ]
