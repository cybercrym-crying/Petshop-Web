from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("product", "0003_rename_image_product_photo"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="stockmutation",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity__gt", 0)),
                name="stockmutation_quantity_gt_0",
            ),
        ),
    ]
