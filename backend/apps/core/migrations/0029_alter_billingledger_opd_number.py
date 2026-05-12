from django.db import migrations, models


def mark_invoiced_open_ledgers_finalized(apps, schema_editor):
	BillingLedger = apps.get_model("core", "BillingLedger")
	BillingInvoice = apps.get_model("core", "BillingInvoice")

	for invoice in BillingInvoice.objects.select_related("ledger").all():
		ledger = invoice.ledger
		if ledger.status != "OPEN":
			continue
		ledger.status = "FINALIZED"
		if not ledger.finalized_at:
			ledger.finalized_at = invoice.created_at
		if not ledger.finalized_by:
			ledger.finalized_by = invoice.created_by or ledger.created_by
		ledger.updated_by = ledger.updated_by or ledger.created_by
		ledger.save(update_fields=["status", "finalized_at", "finalized_by", "updated_by", "updated_at"])


def noop_reverse(apps, schema_editor):
	return None


class Migration(migrations.Migration):

	dependencies = [
		("core", "0028_doctor_opd_existing_patient_fee_and_more"),
	]

	operations = [
		migrations.AlterField(
			model_name="billingledger",
			name="opd_number",
			field=models.CharField(max_length=30),
		),
		migrations.RunPython(mark_invoiced_open_ledgers_finalized, noop_reverse),
		migrations.AddIndex(
			model_name="billingledger",
			index=models.Index(fields=["opd_number"], name="core_billin_opd_num_cdce7a_idx"),
		),
	]