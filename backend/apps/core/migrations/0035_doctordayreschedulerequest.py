from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0034_clinicsettings_upi_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="DoctorDayRescheduleRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_date", models.DateField()),
                ("target_date", models.DateField()),
                ("reason", models.CharField(blank=True, default="", max_length=255)),
                ("total_appointments", models.PositiveIntegerField(default=0)),
                ("target_capacity", models.PositiveIntegerField(default=0)),
                ("target_existing", models.PositiveIntegerField(default=0)),
                ("overflow_count", models.PositiveIntegerField(default=0)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING_RECEPTION", "Pending Reception Decision"),
                            ("EXECUTED_AUTO", "Executed Automatically"),
                            ("EXECUTED_EXCEED", "Executed With Capacity Exceeded"),
                            ("EXECUTED_CASCADE", "Executed With Cascade"),
                        ],
                        default="PENDING_RECEPTION",
                        max_length=40,
                    ),
                ),
                ("requested_by", models.CharField(max_length=150)),
                ("decided_by", models.CharField(blank=True, default="", max_length=150)),
                ("details", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                (
                    "doctor",
                    models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="day_reschedule_requests", to="core.doctor"),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
