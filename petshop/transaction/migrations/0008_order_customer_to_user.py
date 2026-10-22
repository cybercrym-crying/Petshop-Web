"""Order.customer sekarang menunjuk ke User (role CUSTOMER), bukan tabel Customer."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def link_orders_to_users(apps, schema_editor):
    Order = apps.get_model("transaction", "Order")
    User = apps.get_model("account", "User")
    by_phone = dict(
        User.objects.filter(role="CUSTOMER").values_list("phone_number", "pk")
    )
    for order in Order.objects.select_related("customer"):
        user_id = by_phone.get(order.customer.phone_number)
        if user_id is None:
            raise RuntimeError(
                f"Order #{order.pk}: pelanggan {order.customer.phone_number} "
                "tidak ditemukan di tabel user."
            )
        order.customer_user_id = user_id
        order.save(update_fields=["customer_user"])


def unlink_orders(apps, schema_editor):
    Order = apps.get_model("transaction", "Order")
    Customer = apps.get_model("account", "Customer")
    by_phone = dict(Customer.objects.values_list("phone_number", "pk"))
    for order in Order.objects.select_related("customer_user"):
        order.customer_id = by_phone[order.customer_user.phone_number]
        order.save(update_fields=["customer"])


class Migration(migrations.Migration):

    dependencies = [
        ("transaction", "0007_order_tracking_and_delivery_proof"),
        ("account", "0007_user_address_role_customer_kasir_groomer"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="customer_user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(link_orders_to_users, migrations.RunPython.noop),
        migrations.RemoveField(model_name="order", name="customer"),
        migrations.RenameField(
            model_name="order", old_name="customer_user", new_name="customer"
        ),
        migrations.AlterField(
            model_name="order",
            name="customer",
            field=models.ForeignKey(
                limit_choices_to={"role": "CUSTOMER"},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
