from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_doctor_suffix"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClinicSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("clinic_name", models.CharField(default="OPD Clinic", max_length=255)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
