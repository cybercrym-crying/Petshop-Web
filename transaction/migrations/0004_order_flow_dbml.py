import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

ORDER_STATUS = {
    "PENDING": "CONFIRMED",
    "ON DELIVERY": "ON_DELIVERY",
    "SUCCESS": "DELIVERED",
    "FAILED": "CANCELLED",
}
PAYMENT_STATUS = {"SUCCESS": "PAID", "FAILED": "PENDING"}


def forwards(apps, schema_editor):
    Order = apps.get_model("transaction", "Order")
    for old, new in ORDER_STATUS.items():
        Order.objects.filter(order_status=old).update(order_status=new)
    for old, new in PAYMENT_STATUS.items():
        Order.objects.filter(payment_status=old).update(payment_status=new)

    OrderDetail = apps.get_model("transaction", "OrderDetail")
    for d in OrderDetail.objects.filter(quantity__gt=0):
        d.unit_price = d.subtotal // d.quantity
        d.save(update_fields=["unit_price"])


def backwards(apps, schema_editor):
    Order = apps.get_model("transaction", "Order")
    for old, new in ORDER_STATUS.items():
        Order.objects.filter(order_status=new).update(order_status=old)
    Order.objects.filter(payment_status="PAID").update(payment_status="SUCCESS")


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0004_courier_role_unique_phone"),
        ("product", "0004_stockmutation_quantity_gt_0"),
        ("transaction", "0003_alter_order_courir_alter_order_customer"),
    ]

    operations = [
        migrations.RenameField("order", "courir", "courier"),
        migrations.AlterField(
            model_name="order",
            name="courier",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders_as_courier",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="orderdetail",
            name="unit_price",
            field=models.PositiveBigIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="order",
            name="order_status",
            field=models.CharField(
                choices=[
                    ("CONFIRMED", "Confirmed"),
                    ("ON_DELIVERY", "On Delivery"),
                    ("DELIVERED", "Delivered"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="CONFIRMED",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[("PENDING", "Pending"), ("PAID", "Paid")],
                default="PENDING",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="orderdetail",
            name="product",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, to="product.product"
            ),
        ),
        migrations.AddConstraint(
            model_name="orderdetail",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity__gt", 0)),
                name="orderdetail_quantity_gt_0",
            ),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity__gt", 0)),
                name="cartitem_quantity_gt_0",
            ),
        ),
    ]
