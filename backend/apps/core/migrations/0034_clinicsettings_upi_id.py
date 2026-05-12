# Generated migration for ClinicSettings UPI ID field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0033_billinginvoice_payment_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicsettings",
            name="upi_id",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
