from django.db import migrations, models


def to_courier(apps, schema_editor):
    User = apps.get_model("account", "User")
    User.objects.filter(role__in=["KURIR", "COURIR"]).update(role="COURIER")


def from_courier(apps, schema_editor):
    User = apps.get_model("account", "User")
    User.objects.filter(role="COURIER").update(role="COURIR")


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0003_alter_user_role"),
    ]

    operations = [
        migrations.RunPython(to_courier, from_courier),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[("ADMIN", "Admin"), ("COURIER", "Courier")], max_length=20
            ),
        ),
        migrations.AlterField(
            model_name="customer",
            name="phone_number",
            field=models.CharField(max_length=20, unique=True),
        ),
    ]
