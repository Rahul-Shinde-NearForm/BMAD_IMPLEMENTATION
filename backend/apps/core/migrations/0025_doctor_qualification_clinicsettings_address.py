from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_clinicsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctor",
            name="qualification",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="clinicsettings",
            name="clinic_address",
            field=models.TextField(blank=True, default=""),
        ),
    ]
