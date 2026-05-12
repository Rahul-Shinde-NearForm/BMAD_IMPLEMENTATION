from datetime import date, time, timedelta

from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

from .models import Appointment, Doctor, DoctorDayRescheduleRequest, Patient
from .services import (
	add_billing_line_item,
	add_emergency_patient,
	create_or_get_active_billing_ledger,
	finalize_billing_ledger,
	pause_current_consultation,
	set_repeat_fee_decision,
)
from .models import Consultation, QueueItem, QueueEvent


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

	def test_finalize_new_visit_allows_without_opd_fee(self):
		ledger, _ = create_or_get_active_billing_ledger(
			opd_number=self.appointment.opd_number,
			actor_username="reception1",
			appointment_id=self.appointment.id,
		)

		_, invoice_without_fee = finalize_billing_ledger(ledger.id, actor_username="reception1", tax="0", discount="0")
		self.assertEqual(float(invoice_without_fee.total), 0.0)

		ledger, _ = create_or_get_active_billing_ledger(
			opd_number=self.appointment.opd_number,
			actor_username="reception1",
			appointment_id=self.appointment.id,
		)

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


class BillingUnifiedFlowApiTests(TestCase):
	def setUp(self):
		self.reception_group, _ = Group.objects.get_or_create(name="Receptionist")
		self.doctor_group, _ = Group.objects.get_or_create(name="Doctor")

		self.reception_user = User.objects.create_user(username="reception_api", password="x")
		self.reception_user.groups.add(self.reception_group)

		self.doctor_user = User.objects.create_user(username="doctor_api", password="x")
		self.doctor_user.groups.add(self.doctor_group)

		self.doctor = Doctor.objects.create(full_name="Dr API", specialty="General")
		self.patient = Patient.objects.create(
			first_name="Kiran",
			last_name="Patil",
			dob=date(1992, 2, 10),
			gender="M",
			phone="9898989898",
		)
		self.appointment = Appointment.objects.create(
			patient=self.patient,
			doctor=self.doctor,
			slot_date=date.today(),
			start_time=time(11, 0),
			end_time=time(11, 10),
			visit_type="NEW",
			channel="WALK_IN",
			status="BOOKED",
		)

		self.consultation = self.appointment.consultation if hasattr(self.appointment, "consultation") else None
		if self.consultation is None:
			from .models import Consultation, Prescription

			self.consultation = Consultation.objects.create(
				appointment=self.appointment,
				doctor=self.doctor,
				patient=self.patient,
				chief_complaint="Fever",
				diagnosis="Viral fever",
				status="FINALIZED",
				created_by="doctor_api",
				finalized_by="doctor_api",
			)
			Prescription.objects.create(
				consultation=self.consultation,
				patient=self.patient,
				doctor=self.doctor,
				items=[{"drug": "Paracetamol", "dose": "1", "frequency": "BD", "duration": "5"}],
				issued_by="doctor_api",
			)

	def test_receptionist_doctor_unified_billing_then_next_patient_finalizes_invoice(self):
		self.client.force_login(self.reception_user)
		open_res = self.client.post(
			reverse("billing-ledger-by-opd-create"),
			{"opd_number": self.appointment.opd_number, "appointment_id": self.appointment.id},
		)
		self.assertEqual(open_res.status_code, 201)
		open_payload = open_res.json()
		ledger_id = open_payload["data"]["ledger_id"]

		opd_fee_res = self.client.post(
			reverse("billing-ledger-add-line-item", kwargs={"ledger_id": ledger_id}),
			{"line_type": "OPD_NEW_FEE", "amount": "200", "description": "OPD New Fee"},
		)
		self.assertEqual(opd_fee_res.status_code, 201)

		self.client.force_login(self.doctor_user)
		radio_res = self.client.post(
			reverse("billing-ledger-add-line-item", kwargs={"ledger_id": ledger_id}),
			{"line_type": "RADIOLOGY", "amount": "300", "description": "Chest X-ray"},
		)
		self.assertEqual(radio_res.status_code, 201)

		misc_res = self.client.post(
			reverse("billing-ledger-add-line-item", kwargs={"ledger_id": ledger_id}),
			{"line_type": "MISC", "amount": "150", "description": "Medicines"},
		)
		self.assertEqual(misc_res.status_code, 201)

		next_res = self.client.post(
			reverse("appointment-next-patient", kwargs={"consultation_id": self.consultation.id}),
			{},
		)
		self.assertEqual(next_res.status_code, 200)
		next_payload = next_res.json()
		self.assertEqual(next_payload["status"], "COMPLETED")
		self.assertTrue(next_payload["invoice_id"])
		self.assertTrue(next_payload["bill_number"])

		self.client.force_login(self.reception_user)
		invoice_res = self.client.get(reverse("billing-invoice-get", kwargs={"invoice_id": next_payload["invoice_id"]}))
		self.assertEqual(invoice_res.status_code, 200)
		invoice_payload = invoice_res.json()
		self.assertEqual(invoice_payload["data"]["opd_number"], self.appointment.opd_number)
		self.assertEqual(invoice_payload["data"]["totals"]["total"], "650.00")


class EmergencyInterruptWorkflowTests(TestCase):
	def setUp(self):
		self.doctor = Doctor.objects.create(full_name="Dr Rajesh Kumar", specialty="General")
		self.patient_a = Patient.objects.create(
			first_name="Mrs.",
			last_name="Sharma",
			dob=date(1990, 1, 15),
			gender="F",
			phone="9876543210",
		)
		self.patient_b = Patient.objects.create(
			first_name="Mr.",
			last_name="Kumar",
			dob=date(1985, 5, 20),
			gender="M",
			phone="9876543211",
		)
		# Create appointment for patient A
		self.appointment_a = Appointment.objects.create(
			patient=self.patient_a,
			doctor=self.doctor,
			slot_date=date.today(),
			start_time=time(10, 0),
			end_time=time(10, 10),
			visit_type="NEW",
			channel="WALK_IN",
			status="BOOKED",
		)
		# Create queue item for patient A
		self.queue_item_a = QueueItem.objects.create(
			appointment=self.appointment_a,
			doctor=self.doctor,
			slot_date=date.today(),
			token_number=1,
			status="CALLED",  # In progress
			called_at=timezone.now(),
		)
		# Create consultation for patient A
		self.consultation_a = Consultation.objects.create(
			appointment=self.appointment_a,
			doctor=self.doctor,
			patient=self.patient_a,
			chief_complaint="Fever",
			created_by="doctor1",
		)

	def test_pause_current_consultation_success(self):
		"""Test successfully pausing an active consultation"""
		queue_item, event, payload = pause_current_consultation(self.doctor.id, "doctor1")
		
		# Verify queue item status changed to PAUSED
		self.queue_item_a.refresh_from_db()
		self.assertEqual(self.queue_item_a.status, "PAUSED")
		self.assertIsNotNone(self.queue_item_a.paused_at)
		self.assertEqual(self.queue_item_a.paused_by_id, self.doctor.id)
		
		# Verify audit event created
		self.assertIsNotNone(event)
		self.assertEqual(event.action, "PAUSE")
		self.assertEqual(event.previous_status, "CALLED")
		self.assertEqual(event.new_status, "PAUSED")

	def test_pause_no_consultation_in_progress(self):
		"""Test error when trying to pause with no active consultation"""
		# Create a doctor with no active consultation
		doctor_empty = Doctor.objects.create(full_name="Dr Empty", specialty="General")
		
		with self.assertRaises(ValueError) as cm:
			pause_current_consultation(doctor_empty.id, "doctor1")
		self.assertEqual(str(cm.exception), "no_consultation_in_progress")

	def test_pause_finalized_consultation_fails(self):
		"""Test error when trying to pause a finalized consultation"""
		# Finalize the consultation
		self.consultation_a.status = "FINALIZED"
		self.consultation_a.finalized_by = "doctor1"
		self.consultation_a.save()
		
		with self.assertRaises(ValueError) as cm:
			pause_current_consultation(self.doctor.id, "doctor1")
		self.assertEqual(str(cm.exception), "cannot_pause_finalized_consultation")

	def test_add_emergency_patient_existing(self):
		"""Test adding existing patient as emergency"""
		result = add_emergency_patient(
			self.patient_b.id,
			self.doctor.id,
			"receptionist1",
			visit_type="NEW"
		)
		
		# Verify appointment marked as emergency
		self.assertEqual(result["appointment"].is_emergency, True)
		self.assertIsNotNone(result["appointment"].marked_emergency_at)
		
		# Verify queue item created/updated
		self.assertIsNotNone(result["queue_item"])
		self.assertEqual(result["patient_name"], "Mr. Kumar")
		self.assertGreaterEqual(result["queue_position"], 0)

	def test_add_emergency_patient_walkin(self):
		"""Test adding walk-in patient as emergency"""
		patient_data = {
			"first_name": "John",
			"last_name": "Doe",
			"phone": "9999999999",
			"gender": "M",
		}
		
		result = add_emergency_patient(
			patient_data,
			self.doctor.id,
			"receptionist1",
			visit_type="NEW"
		)
		
		# Verify new patient created
		new_patient = Patient.objects.get(phone="9999999999")
		self.assertEqual(new_patient.first_name, "John")
		
		# Verify appointment created with emergency flag
		self.assertEqual(result["appointment"].is_emergency, True)
		self.assertEqual(result["patient_name"], "John Doe")

	def test_call_next_resumes_paused_first(self):
		"""Test that call_next resumes paused items before calling waiting items"""
		from .services import call_next, sync_queue_for_day
		
		# Pause patient A
		pause_current_consultation(self.doctor.id, "doctor1")
		
		# Create and queue patient B as waiting
		appointment_b = Appointment.objects.create(
			patient=self.patient_b,
			doctor=self.doctor,
			slot_date=date.today(),
			start_time=time(10, 15),
			end_time=time(10, 25),
			visit_type="NEW",
			channel="WALK_IN",
			status="BOOKED",
		)
		queue_item_b = QueueItem.objects.create(
			appointment=appointment_b,
			doctor=self.doctor,
			slot_date=date.today(),
			token_number=2,
			status="WAITING",
		)
		
		# Call next should resume patient A (paused)
		queue_item, event, payload = call_next(self.doctor.id, date.today(), "doctor1")
		
		# Verify patient A was resumed
		self.queue_item_a.refresh_from_db()
		self.assertEqual(self.queue_item_a.status, "RESUMED")
		
		# Verify event reflects resumption
		self.assertEqual(event.new_status, "RESUMED")

	def test_call_next_emergency_priority(self):
		"""Test that call_next prioritizes emergency patients over normal waiting"""
		from .services import call_next
		
		# Queue patient A as WAITING (normal)
		self.queue_item_a.status = "WAITING"
		self.queue_item_a.called_at = None
		self.queue_item_a.save()
		
		# Queue patient B as WAITING with emergency flag
		appointment_b = Appointment.objects.create(
			patient=self.patient_b,
			doctor=self.doctor,
			slot_date=date.today(),
			start_time=time(10, 15),
			end_time=time(10, 25),
			visit_type="NEW",
			channel="WALK_IN",
			status="BOOKED",
			is_emergency=True,  # Mark as emergency
		)
		queue_item_b = QueueItem.objects.create(
			appointment=appointment_b,
			doctor=self.doctor,
			slot_date=date.today(),
			token_number=2,
			status="WAITING",
		)
		
		# Call next should get emergency patient (B) even though patient A was created first
		queue_item, event, payload = call_next(self.doctor.id, date.today(), "doctor1")
		
		# Verify patient B (emergency) was called, not patient A (normal)
		self.assertEqual(queue_item.appointment_id, appointment_b.id)
		self.assertEqual(queue_item.status, "CALLED")


class EmergencyInterruptWorkflowApiTests(TestCase):
        def setUp(self):
                self.reception_group, _ = Group.objects.get_or_create(name="Receptionist")
                self.doctor_group, _ = Group.objects.get_or_create(name="Doctor")

                self.reception_user = User.objects.create_user(username="reception_emg", password="x")
                self.reception_user.groups.add(self.reception_group)

                self.doctor_user = User.objects.create_user(username="doctor_emg", password="x")
                self.doctor_user.groups.add(self.doctor_group)

                self.admin_user = User.objects.create_superuser(
                        username="admin_emg",
                        email="admin@example.com",
                        password="x",
                )

                self.doctor = Doctor.objects.create(full_name="Dr Workflow", specialty="General", user=self.doctor_user)
                self.patient = Patient.objects.create(
                        first_name="Seema",
                        last_name="Patel",
                        dob=date(1991, 7, 11),
                        gender="F",
                        phone="9000000001",
                )
                self.waiting_patient = Patient.objects.create(
                        first_name="Arun",
                        last_name="Joshi",
                        dob=date(1989, 3, 2),
                        gender="M",
                        phone="9000000002",
                )

                self.appointment = Appointment.objects.create(
                        patient=self.patient,
                        doctor=self.doctor,
                        slot_date=date.today(),
                        start_time=time(9, 0),
                        end_time=time(9, 10),
                        visit_type="NEW",
                        channel="WALK_IN",
                        status="BOOKED",
                )
                self.queue_item = QueueItem.objects.create(
                        appointment=self.appointment,
                        doctor=self.doctor,
                        slot_date=date.today(),
                        token_number=1,
                        status="CALLED",
                        called_at=timezone.now(),
                )
                Consultation.objects.create(
                        appointment=self.appointment,
                        doctor=self.doctor,
                        patient=self.patient,
                        chief_complaint="Pain",
                        created_by="doctor_emg",
                )

        def test_pause_current_endpoint_doctor_success(self):
                self.client.force_login(self.doctor_user)
                response = self.client.post(reverse("appointment-pause-current"), {})

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["status"], "PAUSED")
                self.assertEqual(payload["appointment_id"], self.appointment.id)

        def test_pause_current_endpoint_requires_doctor_or_admin_role(self):
                self.client.force_login(self.reception_user)
                response = self.client.post(reverse("appointment-pause-current"), {"doctor_id": self.doctor.id})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["error"], "forbidden")

        def test_pause_current_endpoint_admin_requires_doctor_id(self):
                self.client.force_login(self.admin_user)
                response = self.client.post(reverse("appointment-pause-current"), {})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], "doctor_id_required")

        def test_add_emergency_endpoint_existing_patient_success(self):
                self.client.force_login(self.reception_user)
                response = self.client.post(
                        reverse("appointment-add-emergency"),
                        {
                                "doctor_id": self.doctor.id,
                                "patient_id": self.waiting_patient.id,
                                "visit_type": "NEW",
                        },
                )

                self.assertEqual(response.status_code, 201)
                payload = response.json()
                self.assertTrue(payload["is_emergency"])
                self.assertEqual(payload["patient_name"], "Arun Joshi")

                appointment = Appointment.objects.get(id=payload["appointment_id"])
                self.assertTrue(appointment.is_emergency)
                self.assertEqual(appointment.marked_emergency_by_id, self.reception_user.id)

        def test_add_emergency_endpoint_walkin_validation(self):
                self.client.force_login(self.reception_user)
                response = self.client.post(
                        reverse("appointment-add-emergency"),
                        {"doctor_id": self.doctor.id, "first_name": "Walk", "last_name": "In"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], "validation_failed")

        def test_queue_status_alias_includes_status_label_and_emergency(self):
                self.client.force_login(self.reception_user)
                response = self.client.get(
                        reverse("appointments-queue-status"),
                        {"doctor_id": self.doctor.id, "slot_date": date.today().isoformat()},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("items", payload)
                self.assertTrue(payload["items"])
                self.assertIn("status_label", payload["items"][0])
                self.assertIn("is_emergency", payload["items"][0])


class DoctorEmergencyDayUnavailableWorkflowTests(TestCase):
	def setUp(self):
		self.reception_group, _ = Group.objects.get_or_create(name="Receptionist")
		self.doctor_group, _ = Group.objects.get_or_create(name="Doctor")

		self.reception_user = User.objects.create_user(username="reception_day_unavail", password="x")
		self.reception_user.groups.add(self.reception_group)

		self.doctor_user = User.objects.create_user(username="doctor_day_unavail", password="x")
		self.doctor_user.groups.add(self.doctor_group)

		self.doctor = Doctor.objects.create(
			full_name="Dr Day Unavailable",
			specialty="General",
			daily_patient_capacity=2,
			user=self.doctor_user,
		)

		for i in range(3):
			patient = Patient.objects.create(
				first_name=f"Today{i}",
				last_name="Patient",
				dob=date(1990, 1, 1),
				gender="M",
				phone=f"90000010{i}{i}",
			)
			Appointment.objects.create(
				patient=patient,
				doctor=self.doctor,
				slot_date=date.today(),
				start_time=time(9 + i, 0),
				end_time=time(9 + i, 10),
				visit_type="NEW",
				channel="WALK_IN",
				status="BOOKED",
			)

		patient_tomorrow = Patient.objects.create(
			first_name="Tomorrow",
			last_name="Existing",
			dob=date(1992, 1, 1),
			gender="F",
			phone="9000001999",
		)
		tomorrow = timezone.localdate() + timedelta(days=1)
		Appointment.objects.create(
			patient=patient_tomorrow,
			doctor=self.doctor,
			slot_date=tomorrow,
			start_time=time(11, 0),
			end_time=time(11, 10),
			visit_type="NEW",
			channel="WALK_IN",
			status="BOOKED",
		)

	def test_doctor_trigger_creates_pending_request_when_overflow_exists(self):
		self.client.force_login(self.doctor_user)
		response = self.client.post(reverse("doctor-day-unavailable"), {"reason": "Family emergency"})
		self.assertEqual(response.status_code, 202)
		payload = response.json()
		self.assertEqual(payload["status"], "pending_reception_decision")
		self.assertEqual(payload["data"]["overflow_count"], 2)
		self.assertEqual(DoctorDayRescheduleRequest.objects.filter(status="PENDING_RECEPTION").count(), 1)

	def test_reception_decision_cascade_moves_excess_to_next_day(self):
		self.client.force_login(self.doctor_user)
		trigger_res = self.client.post(reverse("doctor-day-unavailable"), {"reason": "Emergency"})
		self.assertEqual(trigger_res.status_code, 202)
		request_id = trigger_res.json()["data"]["request_id"]

		self.client.force_login(self.reception_user)
		pending_res = self.client.get(reverse("reception-day-reschedules-pending"))
		self.assertEqual(pending_res.status_code, 200)
		self.assertEqual(pending_res.json()["count"], 1)

		decision_res = self.client.post(
			reverse("reception-day-reschedules-decide", kwargs={"request_id": request_id}),
			{"action": "CASCADE"},
		)
		self.assertEqual(decision_res.status_code, 200)

		tomorrow = timezone.localdate() + timedelta(days=1)
		next_day = tomorrow + timedelta(days=1)
		tomorrow_count = Appointment.objects.filter(doctor=self.doctor, slot_date=tomorrow).exclude(status="CANCELLED").count()
		next_day_count = Appointment.objects.filter(doctor=self.doctor, slot_date=next_day).exclude(status="CANCELLED").count()

		self.assertEqual(tomorrow_count, 2)
		self.assertEqual(next_day_count, 2)

		request_obj = DoctorDayRescheduleRequest.objects.get(id=request_id)
		self.assertEqual(request_obj.status, "EXECUTED_CASCADE")
