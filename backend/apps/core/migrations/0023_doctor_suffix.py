from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_billingledger_billinginvoice_billingauditevent_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctor",
            name="suffix",
            field=models.CharField(blank=True, default="Dr", max_length=20),
        ),
    ]
