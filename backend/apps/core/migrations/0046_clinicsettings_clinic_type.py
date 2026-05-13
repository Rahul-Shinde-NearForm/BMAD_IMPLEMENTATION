from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0045_phase3_archive_tables"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicsettings",
            name="clinic_type",
            field=models.CharField(
                choices=[("GENERAL", "General"), ("DENTIST", "Dentist")],
                default="GENERAL",
                max_length=20,
            ),
        ),
    ]
