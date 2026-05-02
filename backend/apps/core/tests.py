from datetime import date, time

from django.test import TestCase

from .models import Appointment, Doctor, Patient
from .services import (
	add_billing_line_item,
	create_or_get_active_billing_ledger,
	finalize_billing_ledger,
	set_repeat_fee_decision,
)


class BillingSprintOneServiceTests(TestCase):
	def setUp(self):
		self.doctor = Doctor.objects.create(full_name="Dr Test", specialty="General")
		self.patient = Patient.objects.create(
			first_name="Asha",
			last_name="Patil",
			dob=date(1995, 1, 15),
			gender="F",
			phone="9876543210",
		)
		self.appointment = Appointment.objects.create(
			patient=self.patient,
			doctor=self.doctor,
			slot_date=date.today(),
			start_time=time(10, 0),
			end_time=time(10, 10),
			visit_type="NEW",
			channel="WALK_IN",
			status="BOOKED",
		)

	def test_create_or_get_ledger_is_idempotent(self):
		ledger_one, created_one = create_or_get_active_billing_ledger(
			opd_number=self.appointment.opd_number,
			actor_username="reception1",
			appointment_id=self.appointment.id,
		)
		ledger_two, created_two = create_or_get_active_billing_ledger(
			opd_number=self.appointment.opd_number,
			actor_username="reception1",
			appointment_id=self.appointment.id,
		)

		self.assertTrue(created_one)
		self.assertFalse(created_two)
		self.assertEqual(ledger_one.id, ledger_two.id)

	def test_finalize_new_visit_requires_new_opd_fee(self):
		ledger, _ = create_or_get_active_billing_ledger(
			opd_number=self.appointment.opd_number,
			actor_username="reception1",
			appointment_id=self.appointment.id,
		)

		with self.assertRaisesMessage(ValueError, "mandatory_new_opd_fee_missing"):
			finalize_billing_ledger(ledger.id, actor_username="reception1")

		add_billing_line_item(
			ledger_id=ledger.id,
			line_type="OPD_NEW_FEE",
			amount="500",
			actor_username="reception1",
			description="New OPD fee",
		)
		_, invoice = finalize_billing_ledger(ledger.id, actor_username="reception1", tax="0", discount="0")
		self.assertEqual(str(invoice.total), "500.00")

	def test_repeat_fee_no_requires_reason(self):
		self.appointment.visit_type = "FOLLOW_UP"
		self.appointment.save(update_fields=["visit_type"])
		ledger, _ = create_or_get_active_billing_ledger(
			opd_number=self.appointment.opd_number,
			actor_username="reception1",
			appointment_id=self.appointment.id,
		)

		with self.assertRaisesMessage(ValueError, "repeat_fee_reason_required"):
			set_repeat_fee_decision(ledger.id, decision="NO", actor_username="reception1", reason="")

		updated_ledger = set_repeat_fee_decision(
			ledger.id,
			decision="NO",
			actor_username="reception1",
			reason="Clinic repeat policy waived",
		)
		self.assertEqual(updated_ledger.repeat_fee_decision, "NO")

	def test_create_ledger_accepts_patient_opd_with_appointment_id(self):
		ledger, created = create_or_get_active_billing_ledger(
			opd_number=self.patient.opd_number,
			actor_username="reception1",
			appointment_id=self.appointment.id,
		)

		self.assertTrue(created)
		self.assertEqual(ledger.patient_id, self.patient.id)
		self.assertEqual(ledger.appointment_id, self.appointment.id)

	def test_create_ledger_accepts_patient_opd_without_appointment_id(self):
		ledger, created = create_or_get_active_billing_ledger(
			opd_number=self.patient.opd_number,
			actor_username="reception1",
		)

		self.assertTrue(created)
		self.assertEqual(ledger.patient_id, self.patient.id)
		self.assertEqual(ledger.appointment_id, self.appointment.id)

	def test_finalized_ledger_supports_additional_manual_lab_and_refinalize(self):
		ledger, _ = create_or_get_active_billing_ledger(
			opd_number=self.appointment.opd_number,
			actor_username="reception1",
			appointment_id=self.appointment.id,
		)

		add_billing_line_item(
			ledger_id=ledger.id,
			line_type="OPD_NEW_FEE",
			amount="200",
			actor_username="reception1",
			description="OPD fee",
		)
		finalize_billing_ledger(ledger.id, actor_username="reception1", tax="0", discount="0")

		lab_item = add_billing_line_item(
			ledger_id=ledger.id,
			line_type="MANUAL",
			amount="300",
			actor_username="reception1",
			description="LAB Charges",
		)
		self.assertEqual(lab_item.line_type, "MANUAL")

		ledger.refresh_from_db()
		self.assertEqual(ledger.status, "OPEN")

		_, invoice = finalize_billing_ledger(ledger.id, actor_username="reception1", tax="0", discount="200")
		self.assertEqual(str(invoice.total), "300.00")
