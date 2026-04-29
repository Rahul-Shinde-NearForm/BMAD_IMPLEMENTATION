import logging
from urllib.parse import urlencode
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db import connections
from django.db.utils import OperationalError
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import (
	AppointmentBookForm,
	AppointmentCancelForm,
	AppointmentRescheduleForm,
	ConsultationAmendForm,
	ConsultationDraftForm,
	MedicalOrderForm,
	PatientRegistrationForm,
	PatientUpdateForm,
	QueueBoardForm,
	QueueCallNextForm,
	ScheduleUpsertForm,
	UserCreateForm,
	UserRoleAssignForm,
	VitalsForm,
)
from .models import Appointment, BillingHandoff, Consultation, Doctor, IncidentRecord, MedicalOrder, Patient, Prescription, QueueItem, ReportExport, Vitals
from .authz import role_required
from .services import (
	ROLE_PERMISSION_MATRIX,
	bootstrap_roles,
	book_appointment,
	call_next,
	cancel_appointment,
	complete_appointment,
	create_medical_order,
	create_or_update_consultation_draft,
	daily_kpi_metrics,
	download_report_export,
	doctor_appointments_for_day,
	finalize_consultation,
	amend_consultation,
	issue_prescription,
	generate_report_export,
	create_incident_record,
	patient_opd_history,
	observability_snapshot,
	record_vitals,
	resolve_incident_record,
	find_duplicate_candidates,
	health_payload,
	create_billing_handoff,
	list_billing_handoffs,
	list_queue_board,
	queue_action,
	log_search,
	reschedule_appointment,
	search_patients,
	send_billing_handoff,
	tomorrow_reminder_report,
	upsert_doctor_schedule,
)


audit_logger = logging.getLogger("audit")


def _redirect_user_mgmt(status, message):
	query = urlencode({"status": status, "message": message})
	return redirect(f"/users/manage/?{query}")


def home(request):
	roles = set(request.user.groups.values_list("name", flat=True)) if request.user.is_authenticated else set()
	context = {
		"is_admin": "Admin" in roles,
		"is_doctor": "Doctor" in roles,
		"is_receptionist": "Receptionist" in roles,
		"is_pharmacist": "Pharmacist" in roles,
	}
	return render(request, "home.html", context)


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def receptionist_workbench(request):
	return render(request, "workbench_receptionist.html")


@require_GET
@login_required
@role_required("Doctor", "Admin")
def doctor_workbench(request):
	return render(request, "workbench_doctor.html")


@require_GET
@login_required
@role_required("Pharmacist", "Admin")
def pharmacist_workbench(request):
	return render(request, "workbench_pharmacist.html")


def health(request):
	return JsonResponse(health_payload())


@require_GET
def health_live(request):
	return JsonResponse({"status": "ok", "check": "liveness"})


@require_GET
def health_ready(request):
	# Readiness verifies DB connectivity so orchestrators only route traffic when ready.
	try:
		connections["default"].cursor()
	except OperationalError:
		return JsonResponse({"status": "error", "check": "readiness", "database": "unavailable"}, status=503)
	return JsonResponse({"status": "ok", "check": "readiness", "database": "available"})


@require_POST
@login_required
def rbac_bootstrap(request):
	if not request.user.is_superuser:
		audit_logger.warning("unauthorized_rbac_bootstrap", extra={"user": request.user.username})
		return JsonResponse({"error": "forbidden"}, status=403)

	groups = bootstrap_roles()
	return JsonResponse({"status": "ok", "groups": groups})


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def patient_register(request):
	form = PatientRegistrationForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	duplicates = find_duplicate_candidates(form.cleaned_data)
	if duplicates.exists() and request.POST.get("confirm_duplicate") != "true":
		items = [
			{
				"id": patient.id,
				"full_name": f"{patient.first_name} {patient.last_name}",
				"phone": patient.phone,
				"dob": str(patient.dob),
			}
			for patient in duplicates[:5]
		]
		return JsonResponse({"warning": "possible_duplicate", "duplicates": items}, status=409)

	patient = form.save()
	return JsonResponse(
		{
			"status": "created",
			"patient_id": patient.id,
			"mrn": patient.mrn,
			"uhid": patient.mrn,
		},
		status=201,
	)


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def patient_update(request, patient_id):
	try:
		patient = Patient.objects.get(id=patient_id)
	except Patient.DoesNotExist:
		return JsonResponse({"error": "patient_not_found"}, status=404)

	form = PatientUpdateForm(request.POST, instance=patient)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	updated = form.save()
	return JsonResponse(
		{
			"status": "updated",
			"patient_id": updated.id,
			"mrn": updated.mrn,
			"phone": updated.phone,
		}
	)


@require_GET
@login_required
@role_required("Receptionist", "Doctor", "Admin")
def patient_opd_history_view(request, patient_id):
	try:
		patient = Patient.objects.get(id=patient_id)
	except Patient.DoesNotExist:
		return JsonResponse({"error": "patient_not_found"}, status=404)

	history = patient_opd_history(patient_id)
	return JsonResponse(
		{
			"patient_id": patient.id,
			"patient_name": f"{patient.first_name} {patient.last_name}",
			"mrn": patient.mrn,
			"opd_history": [
				{
					"appointment_id": a.id,
					"opd_number": a.opd_number,
					"slot_date": str(a.slot_date),
					"doctor_id": a.doctor_id,
					"status": a.status,
				}
				for a in history
			],
		}
	)


@require_GET
@login_required
def patient_register_form(request):
	form = PatientRegistrationForm()
	return render(request, "patient_register.html", {"form": form})


@require_GET
@login_required
@role_required("Receptionist", "Doctor", "Pharmacist", "Admin")
def patient_search(request):
	mrn = request.GET.get("mrn", "").strip()
	phone = request.GET.get("phone", "").strip()
	name = request.GET.get("name", "").strip()
	dob = request.GET.get("dob", "").strip()

	patients = search_patients(mrn=mrn, phone=phone, name=name, dob=dob)
	items = [
		{
			"id": patient.id,
			"mrn": patient.mrn,
			"full_name": f"{patient.first_name} {patient.last_name}",
			"phone": patient.phone,
			"dob": str(patient.dob),
		}
		for patient in patients[:20]
	]

	query_type = "mrn" if mrn else "phone" if phone else "name_dob" if (name or dob) else "none"
	query_value = mrn or phone or f"{name}|{dob}"
	log_search(request.user.username, query_type, query_value, len(items))

	return JsonResponse({"items": items})


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def schedule_upsert(request):
	form = ScheduleUpsertForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	result = upsert_doctor_schedule(form.cleaned_data, request.user.username)
	return JsonResponse({"status": "ok", **result})


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def appointment_book(request):
	form = AppointmentBookForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		appointment = book_appointment(form.cleaned_data, request.user.username)
	except (Patient.DoesNotExist, Doctor.DoesNotExist):
		return JsonResponse({"error": "entity_not_found"}, status=404)
	except Exception as exc:
		if str(exc) in {"invalid_slot", "overbooking_limit_reached"}:
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	history = [
		{
			"appointment_id": a.id,
			"opd_number": a.opd_number,
			"slot_date": str(a.slot_date),
			"status": a.status,
		}
		for a in patient_opd_history(appointment.patient_id)
		if a.id != appointment.id
	]
	return JsonResponse(
		{
			"status": "BOOKED",
			"appointment_id": appointment.id,
			"opd_number": appointment.opd_number,
			"patient_mrn": appointment.patient.mrn,
			"previous_opd_history": history,
		},
		status=201,
	)


@require_POST
@login_required
@role_required("Doctor", "Admin")
def appointment_complete(request, appointment_id):
	try:
		appointment = Appointment.objects.get(id=appointment_id)
		updated = complete_appointment(appointment, request.user.username)
	except Appointment.DoesNotExist:
		return JsonResponse({"error": "appointment_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) == "invalid_transition":
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	return JsonResponse({"status": updated.status, "appointment_id": updated.id, "opd_number": updated.opd_number})


@require_GET
@login_required
@role_required("Doctor", "Admin")
def doctor_today_appointments(request):
	doctor_id = request.GET.get("doctor_id")
	if not doctor_id:
		return JsonResponse({"error": "doctor_id_required"}, status=400)
	try:
		doctor = Doctor.objects.get(id=doctor_id)
	except Doctor.DoesNotExist:
		return JsonResponse({"error": "doctor_not_found"}, status=404)

	from django.utils import timezone
	for_date = timezone.localdate()
	appointments = doctor_appointments_for_day(doctor.id, for_date)
	return JsonResponse(
		{
			"doctor_id": doctor.id,
			"doctor_name": doctor.full_name,
			"date": str(for_date),
			"appointments": [
				{
					"appointment_id": a.id,
					"opd_number": a.opd_number,
					"patient_id": a.patient_id,
					"patient_name": f"{a.patient.first_name} {a.patient.last_name}",
					"mobile": a.patient.phone,
					"start_time": a.start_time.strftime("%H:%M"),
					"end_time": a.end_time.strftime("%H:%M"),
					"status": a.status,
				}
				for a in appointments
			],
		}
	)


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def tomorrow_reminder_report_view(request):
	doctor_id = request.GET.get("doctor_id")
	target_date, items = tomorrow_reminder_report(doctor_id=doctor_id)
	return JsonResponse(
		{
			"date": str(target_date),
			"count": len(items),
			"patients": [
				{
					"appointment_id": a.id,
					"opd_number": a.opd_number,
					"patient_name": f"{a.patient.first_name} {a.patient.last_name}",
					"mobile": a.patient.phone,
					"doctor_name": a.doctor.full_name,
					"slot_time": a.start_time.strftime("%H:%M"),
				}
				for a in items
			],
		}
	)


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def appointment_reschedule(request, appointment_id):
	form = AppointmentRescheduleForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		appointment = Appointment.objects.get(id=appointment_id)
		updated = reschedule_appointment(appointment, form.cleaned_data, request.user.username)
	except Appointment.DoesNotExist:
		return JsonResponse({"error": "appointment_not_found"}, status=404)
	except Exception as exc:
		if str(exc) in {"invalid_transition", "invalid_slot", "overbooking_limit_reached"}:
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	return JsonResponse({"status": updated.status, "appointment_id": updated.id})


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def appointment_cancel(request, appointment_id):
	form = AppointmentCancelForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		appointment = Appointment.objects.get(id=appointment_id)
		updated = cancel_appointment(appointment, form.cleaned_data["reason"], request.user.username)
	except Appointment.DoesNotExist:
		return JsonResponse({"error": "appointment_not_found"}, status=404)
	except Exception as exc:
		if str(exc) == "invalid_transition":
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	return JsonResponse({"status": updated.status, "appointment_id": updated.id})


@require_GET
@login_required
@role_required("Admin")
def user_role_management(request):
	users = User.objects.all().order_by("username")
	roles = sorted(ROLE_PERMISSION_MATRIX.keys())
	user_rows = []
	for user in users:
		user_rows.append(
			{
				"id": user.id,
				"username": user.username,
				"roles": [group.name for group in user.groups.all()],
			}
		)

	return render(
		request,
		"user_role_management.html",
		{
			"users": user_rows,
			"roles": roles,
			"create_form": UserCreateForm(),
			"assign_form": UserRoleAssignForm(),
			"message": request.GET.get("message", ""),
			"status": request.GET.get("status", ""),
		},
	)


@require_POST
@login_required
@role_required("Admin")
def user_create(request):
	form = UserCreateForm(request.POST)
	roles = sorted(ROLE_PERMISSION_MATRIX.keys())
	if not form.is_valid() or form.cleaned_data["role"] not in roles:
		return _redirect_user_mgmt("error", "User creation failed. Check input values.")

	user = User.objects.create_user(
		username=form.cleaned_data["username"],
		password=form.cleaned_data["password"],
	)
	group, _ = Group.objects.get_or_create(name=form.cleaned_data["role"])
	user.groups.set([group])
	return _redirect_user_mgmt("success", f"User {user.username} created with role {group.name}.")


@require_POST
@login_required
@role_required("Admin")
def user_assign_role(request):
	form = UserRoleAssignForm(request.POST)
	roles = sorted(ROLE_PERMISSION_MATRIX.keys())
	if not form.is_valid() or form.cleaned_data["role"] not in roles:
		return _redirect_user_mgmt("error", "Role assignment failed. Check input values.")

	try:
		user = User.objects.get(id=form.cleaned_data["user_id"])
	except User.DoesNotExist:
		return _redirect_user_mgmt("error", "Selected user was not found.")

	group, _ = Group.objects.get_or_create(name=form.cleaned_data["role"])
	user.groups.set([group])
	return _redirect_user_mgmt("success", f"Role for {user.username} updated to {group.name}.")


@require_GET
@login_required
@role_required("Receptionist", "Doctor", "Admin")
def queue_board(request):
	form = QueueBoardForm(request.GET)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	items = list_queue_board(
		doctor_id=form.cleaned_data["doctor_id"],
		slot_date=form.cleaned_data["slot_date"],
	)
	return JsonResponse({"items": items})


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def queue_call_next(request):
	form = QueueCallNextForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		queue_item, _, payload = call_next(
			doctor_id=form.cleaned_data["doctor_id"],
			slot_date=form.cleaned_data["slot_date"],
			actor_username=request.user.username,
		)
	except ValueError as exc:
		if str(exc) == "queue_empty":
			return JsonResponse({"error": "queue_empty"}, status=409)
		raise

	return JsonResponse(
		{
			"status": queue_item.status,
			"queue_item_id": queue_item.id,
			"event": payload,
		}
	)


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def queue_skip(request, queue_item_id):
	try:
		queue_item, _, payload = queue_action(queue_item_id, "SKIP", request.user.username)
	except QueueItem.DoesNotExist:
		return JsonResponse({"error": "queue_item_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) in {"invalid_transition", "invalid_action"}:
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	return JsonResponse({"status": queue_item.status, "queue_item_id": queue_item.id, "event": payload})


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def queue_recall(request, queue_item_id):
	try:
		queue_item, _, payload = queue_action(queue_item_id, "RECALL", request.user.username)
	except QueueItem.DoesNotExist:
		return JsonResponse({"error": "queue_item_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) in {"invalid_transition", "invalid_action"}:
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	return JsonResponse({"status": queue_item.status, "queue_item_id": queue_item.id, "event": payload})


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def queue_no_show(request, queue_item_id):
	try:
		queue_item, _, payload = queue_action(queue_item_id, "NO_SHOW", request.user.username)
	except QueueItem.DoesNotExist:
		return JsonResponse({"error": "queue_item_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) in {"invalid_transition", "invalid_action"}:
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	return JsonResponse({"status": queue_item.status, "queue_item_id": queue_item.id, "event": payload})


@require_POST
@login_required
@role_required("Doctor", "Admin")
def consultation_save_draft(request, appointment_id):
	form = ConsultationDraftForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		consultation = create_or_update_consultation_draft(
			appointment_id=appointment_id,
			data={k: v for k, v in form.cleaned_data.items() if v not in (None, "")},
			actor_username=request.user.username,
		)
	except Appointment.DoesNotExist:
		return JsonResponse({"error": "appointment_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) == "already_finalized":
			return JsonResponse({"error": "already_finalized"}, status=409)
		raise

	return JsonResponse(
		{
			"status": consultation.status,
			"consultation_id": consultation.id,
			"appointment_id": appointment_id,
		}
	)


@require_POST
@login_required
@role_required("Doctor", "Admin")
def consultation_finalize(request, consultation_id):
	try:
		consultation = finalize_consultation(
			consultation_id=consultation_id,
			actor_username=request.user.username,
		)
	except Consultation.DoesNotExist:
		return JsonResponse({"error": "consultation_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) == "already_finalized":
			return JsonResponse({"error": "already_finalized"}, status=409)
		raise

	return JsonResponse(
		{
			"status": consultation.status,
			"consultation_id": consultation.id,
			"finalized_by": consultation.finalized_by,
		}
	)


@require_GET
@login_required
@role_required("Doctor", "Receptionist", "Admin")
def consultation_get(request, appointment_id):
	try:
		consultation = Consultation.objects.get(appointment_id=appointment_id)
	except Consultation.DoesNotExist:
		return JsonResponse({"error": "not_found"}, status=404)

	return JsonResponse(
		{
			"consultation_id": consultation.id,
			"appointment_id": appointment_id,
			"status": consultation.status,
			"chief_complaint": consultation.chief_complaint,
			"findings": consultation.findings,
			"diagnosis": consultation.diagnosis,
			"notes": consultation.notes,
			"follow_up_date": str(consultation.follow_up_date) if consultation.follow_up_date else None,
			"finalized_by": consultation.finalized_by,
			"finalized_at": consultation.finalized_at.isoformat() if consultation.finalized_at else None,
		}
	)


@require_POST
@login_required
@role_required("Doctor", "Receptionist", "Admin")
def vitals_record(request, consultation_id):
	form = VitalsForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		vitals = record_vitals(consultation_id, form.cleaned_data, request.user.username)
	except Consultation.DoesNotExist:
		return JsonResponse({"error": "consultation_not_found"}, status=404)

	return JsonResponse(
		{
			"vitals_id": vitals.id,
			"consultation_id": consultation_id,
			"recorded_by": vitals.recorded_by,
		}
	)


@require_POST
@login_required
@role_required("Doctor", "Admin")
def consultation_amend(request, consultation_id):
	form = ConsultationAmendForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		amendment = amend_consultation(
			consultation_id=consultation_id,
			field_name=form.cleaned_data["field_name"],
			new_value=form.cleaned_data["new_value"],
			reason=form.cleaned_data["reason"],
			actor_username=request.user.username,
		)
	except Consultation.DoesNotExist:
		return JsonResponse({"error": "consultation_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) in {"invalid_field", "not_finalized"}:
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	return JsonResponse(
		{
			"amendment_id": amendment.id,
			"consultation_id": consultation_id,
			"field_name": amendment.field_name,
			"previous_value": amendment.previous_value,
			"new_value": amendment.new_value,
			"reason": amendment.reason,
		}
	)


@require_GET
@login_required
@role_required("Doctor", "Admin")
def consultation_amendment_history(request, consultation_id):
	try:
		consultation = Consultation.objects.get(id=consultation_id)
	except Consultation.DoesNotExist:
		return JsonResponse({"error": "consultation_not_found"}, status=404)

	amendments = consultation.amendments.all().order_by("created_at")
	return JsonResponse(
		{
			"consultation_id": consultation_id,
			"amendments": [
				{
					"id": a.id,
					"field_name": a.field_name,
					"previous_value": a.previous_value,
					"new_value": a.new_value,
					"reason": a.reason,
					"actor_username": a.actor_username,
					"created_at": a.created_at.isoformat(),
				}
				for a in amendments
			],
		}
	)


@require_POST
@login_required
@role_required("Doctor", "Admin")
def prescription_issue(request, consultation_id):
	import json
	try:
		payload = json.loads(request.body)
		if not isinstance(payload, dict):
			raise ValueError
	except (ValueError, KeyError):
		return JsonResponse({"error": "invalid_json"}, status=400)

	try:
		prescription = issue_prescription(consultation_id, payload, request.user.username)
	except Consultation.DoesNotExist:
		return JsonResponse({"error": "consultation_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=409)

	return JsonResponse(
		{
			"prescription_id": prescription.id,
			"rx_number": prescription.rx_number,
			"consultation_id": consultation_id,
			"items": prescription.items,
			"issued_by": prescription.issued_by,
			"issued_at": prescription.issued_at.isoformat(),
		},
		status=201,
	)


@require_GET
@login_required
@role_required("Doctor", "Pharmacist", "Admin")
def prescription_get(request, consultation_id):
	try:
		p = Prescription.objects.select_related("patient", "doctor", "consultation").get(consultation_id=consultation_id)
	except Prescription.DoesNotExist:
		return JsonResponse({"error": "not_found"}, status=404)

	patient = p.patient
	doctor = p.doctor
	consultation = p.consultation

	# Indian prescription format response
	return JsonResponse(
		{
			# --- Header (Doctor / Clinic) ---
			"rx_number": p.rx_number,
			"issued_at": p.issued_at.strftime("%d/%m/%Y %H:%M"),
			"validity_days": p.validity_days,
			"doctor": {
				"name": doctor.full_name,
				"specialty": doctor.specialty,
				"qualification": p.doctor_qualification,
				"reg_number": p.doctor_reg_number,
			},
			"clinic": {
				"name": p.clinic_name,
				"address": p.clinic_address,
			},
			# --- Patient Section ---
			"patient": {
				"name": f"{patient.first_name} {patient.last_name}",
				"age": p.patient_age_at_issue,
				"sex": patient.get_gender_display(),
				"weight_kg": str(p.patient_weight_kg) if p.patient_weight_kg else None,
				"phone": patient.phone,
			},
			# --- Clinical context ---
			"diagnosis": consultation.diagnosis,
			# --- Rx Items (Rp.) ---
			"items": [
				{
					"sno": idx + 1,
					"drug": item.get("drug"),
					"dosage_form": item.get("dosage_form"),
					"strength": item.get("strength"),
					"dose": item.get("dose"),
					"frequency": item.get("frequency"),
					"duration": item.get("duration"),
					"timing": item.get("timing"),
					"route": item.get("route"),
					"instructions": item.get("instructions", ""),
				}
				for idx, item in enumerate(p.items)
			],
			# --- Footer ---
			"special_instructions": p.special_instructions,
			"issued_by": p.issued_by,
			"disclaimer": "This prescription is valid for pharmacy dispensing within the validity period as per Indian prescription regulations.",
		}
	)


@require_GET
@login_required
@role_required("Doctor", "Pharmacist", "Admin")
def prescription_print(request, consultation_id):
	try:
		p = Prescription.objects.select_related("patient", "doctor", "consultation").get(consultation_id=consultation_id)
	except Prescription.DoesNotExist:
		return JsonResponse({"error": "not_found"}, status=404)

	patient = p.patient
	doctor = p.doctor
	consultation = p.consultation
	context = {
		"rx_number": p.rx_number,
		"issued_at": p.issued_at,
		"validity_days": p.validity_days,
		"doctor_name": doctor.full_name,
		"doctor_specialty": doctor.specialty,
		"doctor_qualification": p.doctor_qualification,
		"doctor_reg_number": p.doctor_reg_number,
		"clinic_name": p.clinic_name,
		"clinic_address": p.clinic_address,
		"patient_name": f"{patient.first_name} {patient.last_name}",
		"patient_mrn": patient.mrn,
		"patient_age": p.patient_age_at_issue,
		"patient_gender": patient.get_gender_display(),
		"patient_weight_kg": p.patient_weight_kg,
		"patient_phone": patient.phone,
		"diagnosis": consultation.diagnosis,
		"items": p.items,
		"special_instructions": p.special_instructions,
		"issued_by": p.issued_by,
	}
	return render(request, "prescription_print.html", context)


@require_POST
@login_required
@role_required("Doctor", "Admin")
def medical_order_create(request, consultation_id):
	form = MedicalOrderForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		order = create_medical_order(
			consultation_id=consultation_id,
			order_type=form.cleaned_data["order_type"],
			description=form.cleaned_data["description"],
			actor_username=request.user.username,
		)
	except Consultation.DoesNotExist:
		return JsonResponse({"error": "consultation_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=409)

	return JsonResponse(
		{
			"order_id": order.id,
			"consultation_id": consultation_id,
			"order_type": order.order_type,
			"description": order.description,
			"status": order.status,
		},
		status=201,
	)


@require_GET
@login_required
@role_required("Doctor", "Pharmacist", "Admin")
def medical_order_list(request, consultation_id):
	orders = MedicalOrder.objects.filter(consultation_id=consultation_id).order_by("created_at")
	return JsonResponse(
		{
			"consultation_id": consultation_id,
			"orders": [
				{
					"order_id": o.id,
					"order_type": o.order_type,
					"description": o.description,
					"status": o.status,
					"created_by": o.created_by,
					"created_at": o.created_at.isoformat(),
				}
				for o in orders
			],
		}
	)


# ---------------------------------------------------------------------------
# Billing handoff — Epic 4 (Stories 4.1 / 4.2 / 4.3)
# ---------------------------------------------------------------------------

@login_required
@require_POST
@role_required("Doctor", "Admin")
def billing_handoff_create(request, consultation_id):
	try:
		handoff = create_billing_handoff(consultation_id, request.user.username)
	except Consultation.DoesNotExist:
		return JsonResponse({"error": "consultation_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=400)
	return JsonResponse(
		{
			"handoff_id": handoff.id,
			"status": handoff.status,
			"consultation_id": consultation_id,
			"patient_mrn": handoff.patient.mrn,
			"triggered_by": handoff.triggered_by,
			"created_at": handoff.created_at.isoformat(),
		},
		status=201,
	)


@login_required
@require_POST
@role_required("Admin")
def billing_handoff_send(request, handoff_id):
	try:
		handoff = send_billing_handoff(handoff_id, actor_username=request.user.username)
	except BillingHandoff.DoesNotExist:
		return JsonResponse({"error": "handoff_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=400)
	return JsonResponse(
		{
			"handoff_id": handoff.id,
			"status": handoff.status,
			"retry_count": handoff.retry_count,
			"failure_reason": handoff.failure_reason,
			"next_retry_at": handoff.next_retry_at.isoformat() if handoff.next_retry_at else None,
		}
	)


@login_required
@require_GET
@role_required("Admin")
def billing_handoff_reconcile(request):
	status_filter = request.GET.get("status")
	date_from = request.GET.get("date_from")
	date_to = request.GET.get("date_to")
	handoffs = list_billing_handoffs(status=status_filter, date_from=date_from, date_to=date_to)
	return JsonResponse(
		{
			"count": len(handoffs),
			"results": [
				{
					"handoff_id": h.id,
					"consultation_id": h.consultation_id,
					"patient_mrn": h.patient.mrn,
					"status": h.status,
					"retry_count": h.retry_count,
					"failure_reason": h.failure_reason,
					"next_retry_at": h.next_retry_at.isoformat() if h.next_retry_at else None,
					"triggered_by": h.triggered_by,
					"created_at": h.created_at.isoformat(),
				}
				for h in handoffs
			],
		}
	)


@login_required
@require_GET
@role_required("Admin")
def dashboard_daily_metrics(request):
	date_value = request.GET.get("date")
	specialty = request.GET.get("specialty")
	doctor_id = request.GET.get("doctor_id")
	location = request.GET.get("location")

	try:
		report_date = datetime.strptime(date_value, "%Y-%m-%d").date() if date_value else None
	except ValueError:
		return JsonResponse({"error": "invalid_date_format"}, status=400)

	if report_date is None:
		from django.utils import timezone
		report_date = timezone.localdate()

	if doctor_id is not None:
		try:
			int(doctor_id)
		except ValueError:
			return JsonResponse({"error": "invalid_doctor_id"}, status=400)

	data = daily_kpi_metrics(
		report_date=report_date,
		specialty=specialty,
		doctor_id=doctor_id,
		location=location,
	)
	return JsonResponse(data)


@login_required
@require_POST
@role_required("Admin")
def report_export_generate(request):
	import json
	try:
		payload = json.loads(request.body) if request.body else {}
		if not isinstance(payload, dict):
			raise ValueError
	except ValueError:
		return JsonResponse({"error": "invalid_json"}, status=400)

	export_format = (payload.get("format") or "").upper()
	filters = payload.get("filters") or {}
	if not isinstance(filters, dict):
		return JsonResponse({"error": "invalid_filters"}, status=400)

	try:
		export = generate_report_export(export_format, filters, request.user.username)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=400)

	return JsonResponse(
		{
			"export_id": export.id,
			"format": export.format,
			"artifact_name": export.artifact_name,
			"status": export.status,
			"created_at": export.created_at.isoformat(),
		},
		status=201,
	)


@login_required
@require_GET
@role_required("Admin")
def report_export_list(request):
	items = ReportExport.objects.all().order_by("-created_at")[:100]
	return JsonResponse(
		{
			"count": len(items),
			"exports": [
				{
					"export_id": item.id,
					"format": item.format,
					"artifact_name": item.artifact_name,
					"status": item.status,
					"download_count": item.download_count,
					"last_downloaded_at": item.last_downloaded_at.isoformat() if item.last_downloaded_at else None,
					"created_at": item.created_at.isoformat(),
				}
				for item in items
			],
		}
	)


@login_required
@require_GET
@role_required("Admin")
def report_export_download(request, export_id):
	try:
		export = download_report_export(export_id, request.user.username)
	except ReportExport.DoesNotExist:
		return JsonResponse({"error": "export_not_found"}, status=404)

	if export.format == "CSV":
		content_type = "text/csv"
	else:
		content_type = "application/pdf"

	response = HttpResponse(export.artifact_content, content_type=content_type)
	response["Content-Disposition"] = f'attachment; filename="{export.artifact_name}"'
	return response


@login_required
@require_GET
@role_required("Admin")
def observability_snapshot_view(request):
	queue_lag_threshold = request.GET.get("queue_lag_threshold", 25)
	billing_backlog_threshold = request.GET.get("billing_backlog_threshold", 10)
	try:
		queue_lag_threshold = float(queue_lag_threshold)
		billing_backlog_threshold = float(billing_backlog_threshold)
	except ValueError:
		return JsonResponse({"error": "invalid_threshold"}, status=400)

	data = observability_snapshot(
		actor_username=request.user.username,
		queue_lag_threshold=queue_lag_threshold,
		billing_backlog_threshold=billing_backlog_threshold,
	)
	return JsonResponse(data)


@login_required
@require_POST
@role_required("Admin")
def incident_create_view(request):
	import json
	try:
		payload = json.loads(request.body) if request.body else {}
		if not isinstance(payload, dict):
			raise ValueError
	except ValueError:
		return JsonResponse({"error": "invalid_json"}, status=400)

	try:
		incident = create_incident_record(
			severity=payload.get("severity", "WARN"),
			source=payload.get("source", "manual"),
			summary=payload.get("summary", "Manual incident"),
			runbook_ref=payload.get("runbook_ref", ""),
			details=payload.get("details", {}),
			actor_username=request.user.username,
		)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=400)

	return JsonResponse(
		{
			"incident_id": incident.id,
			"status": incident.status,
			"severity": incident.severity,
			"source": incident.source,
			"summary": incident.summary,
			"runbook_ref": incident.runbook_ref,
		},
		status=201,
	)


@login_required
@require_POST
@role_required("Admin")
def incident_resolve_view(request, incident_id):
	try:
		incident = resolve_incident_record(incident_id, request.user.username)
	except IncidentRecord.DoesNotExist:
		return JsonResponse({"error": "incident_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=409)

	return JsonResponse(
		{
			"incident_id": incident.id,
			"status": incident.status,
			"resolved_by": incident.resolved_by,
			"resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
		}
	)


@login_required
@require_GET
@role_required("Admin")
def incident_list_view(request):
	status_filter = request.GET.get("status")
	items = IncidentRecord.objects.all().order_by("-created_at")
	if status_filter:
		items = items.filter(status=status_filter)
	items = list(items[:200])
	return JsonResponse(
		{
			"count": len(items),
			"incidents": [
				{
					"incident_id": i.id,
					"severity": i.severity,
					"source": i.source,
					"summary": i.summary,
					"runbook_ref": i.runbook_ref,
					"status": i.status,
					"created_by": i.created_by,
					"resolved_by": i.resolved_by,
					"created_at": i.created_at.isoformat(),
					"resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
				}
				for i in items
			],
		}
	)
