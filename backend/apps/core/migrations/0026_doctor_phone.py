from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_doctor_qualification_clinicsettings_address"),
    ]

    operations = [
        migrations.AddField(
            model_name="doctor",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
    ]
