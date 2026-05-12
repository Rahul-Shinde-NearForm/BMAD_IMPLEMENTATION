# Generated migration for RCT multi-sitting recovery tracking

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0036_billinginvoice_partial_recovery'),
    ]

    operations = [
        migrations.AddField(
            model_name='billinglineitem',
            name='total_case_amount',
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='billinglineitem',
            name='recovery_stage_percent',
            field=models.PositiveSmallIntegerField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name='billinglineitem',
            name='sitting_number',
            field=models.PositiveSmallIntegerField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name='billinglineitem',
            name='total_sittings',
            field=models.PositiveSmallIntegerField(blank=True, default=None, null=True),
        ),
    ]
