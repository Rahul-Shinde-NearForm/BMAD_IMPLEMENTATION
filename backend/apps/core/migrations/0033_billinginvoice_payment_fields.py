from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_appointment_is_emergency_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="billinginvoice",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="billinginvoice",
            name="payment_method",
            field=models.CharField(blank=True, choices=[("", "Unknown"), ("UPI", "UPI"), ("CASH", "Cash"), ("CARD", "Card")], default="", max_length=20),
        ),
        migrations.AddField(
            model_name="billinginvoice",
            name="payment_status",
            field=models.CharField(choices=[("PENDING", "Pending"), ("DONE", "Done")], default="PENDING", max_length=20),
        ),
        migrations.AddField(
            model_name="billinginvoice",
            name="upi_txn_ref",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
