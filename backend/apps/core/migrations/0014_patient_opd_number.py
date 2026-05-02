from django.db import migrations, models


def backfill_patient_opd_numbers(apps, schema_editor):
    Patient = apps.get_model("core", "Patient")
    for patient in Patient.objects.filter(opd_number=""):
        patient.opd_number = f"OPDP-{patient.pk:06d}"
        patient.save(update_fields=["opd_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_alertevent_incidentrecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="patient",
            name="opd_number",
            field=models.CharField(blank=True, default="", max_length=30, unique=True),
        ),
        migrations.RunPython(backfill_patient_opd_numbers, migrations.RunPython.noop),
    ]
