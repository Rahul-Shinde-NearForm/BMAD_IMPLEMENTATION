from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_doctor_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicsettings",
            name="logo",
            field=models.ImageField(blank=True, null=True, upload_to="clinic_logos/"),
        ),
        migrations.AddField(
            model_name="clinicsettings",
            name="registration_number",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="clinicsettings",
            name="registration_authority",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="prescription",
            name="clinic_logo_url",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.AddField(
            model_name="prescription",
            name="clinic_registration_number",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="prescription",
            name="clinic_registration_authority",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
