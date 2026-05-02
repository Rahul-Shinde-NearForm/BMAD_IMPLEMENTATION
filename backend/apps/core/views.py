import json
import logging
from urllib.parse import urlencode
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db import connections
from django.db.models import Q
from django.db.utils import OperationalError
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
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
from .models import Appointment, BillingHandoff, BillingInvoice, BillingLedger, BillingLineItem, ClinicSettings, Consultation, Doctor, DoctorSlot, IncidentRecord, MedicalOrder, Patient, Prescription, QueueItem, ReportExport, Vitals
from .authz import role_required
from .services import (
	ROLE_PERMISSION_MATRIX,
	bootstrap_roles,
	book_appointment,
	call_next,
	cancel_appointment,
	complete_appointment,
	create_medical_order,
	create_medical_order_for_patient,
	create_or_update_consultation_draft,
	daily_kpi_metrics,
	download_report_export,
	doctor_appointments_for_day,
	finalize_consultation,
	amend_consultation,
	issue_prescription,
	update_prescription,
	generate_report_export,
	create_incident_record,
	patient_opd_history,
	observability_snapshot,
	get_doctor_capacity_for_date,
	record_vitals,
	resolve_incident_record,
	find_duplicate_candidates,
	health_payload,
	create_billing_handoff,
	create_or_get_active_billing_ledger,
	list_billing_handoffs,
	add_billing_line_item,
	list_queue_board,
	finalize_billing_ledger,
	queue_action,
	queue_mark_called_for_appointment,
	log_search,
	reschedule_appointment,
	search_patients,
	sync_queue_for_day,
	send_billing_handoff,
	set_repeat_fee_decision,
	tomorrow_reminder_report,
	upsert_doctor_schedule,
)


audit_logger = logging.getLogger("audit")


def _billing_line_item_payload(item):
	return {
		"line_item_id": item.id,
		"line_type": item.line_type,
		"description": item.description,
		"amount": str(item.amount),
		"source_order_id": item.source_order_id,
		"created_by": item.created_by,
		"created_at": item.created_at.isoformat(),
	}


def _billing_ledger_payload(ledger):
	return {
		"ledger_id": ledger.id,
		"opd_number": ledger.opd_number,
		"appointment_id": ledger.appointment_id,
		"patient_id": ledger.patient_id,
		"doctor_id": ledger.doctor_id,
		"visit_date": str(ledger.visit_date),
		"visit_type": ledger.visit_type,
		"status": ledger.status,
		"repeat_fee_decision": ledger.repeat_fee_decision,
		"repeat_fee_reason": ledger.repeat_fee_reason,
		"finalized_by": ledger.finalized_by,
		"finalized_at": ledger.finalized_at.isoformat() if ledger.finalized_at else None,
		"line_items": [_billing_line_item_payload(item) for item in ledger.line_items.all()],
		"invoice": {
			"invoice_id": ledger.invoice.id,
			"bill_number": ledger.invoice.bill_number,
			"subtotal": str(ledger.invoice.subtotal),
			"discount": str(ledger.invoice.discount),
			"tax": str(ledger.invoice.tax),
			"total": str(ledger.invoice.total),
			"created_at": ledger.invoice.created_at.isoformat(),
		} if hasattr(ledger, "invoice") else None,
	}


def _opd_clinic_name():
	return ClinicSettings.get_solo().clinic_name


def _opd_clinic_address():
	return ClinicSettings.get_solo().clinic_address


def _invoice_print_context(invoice, auto_print=False):
	line_items = BillingLineItem.objects.filter(ledger_id=invoice.ledger_id).order_by("created_at")
	return {
		"auto_print": auto_print,
		"clinic_name": _opd_clinic_name(),
		"clinic_address": _opd_clinic_address(),
		"invoice_id": invoice.id,
		"bill_number": invoice.bill_number,
		"created_at": invoice.created_at,
		"opd_number": invoice.ledger.opd_number,
		"visit_date": invoice.ledger.visit_date,
		"patient_name": f"{invoice.ledger.patient.first_name} {invoice.ledger.patient.last_name}".strip(),
		"patient_phone": invoice.ledger.patient.phone,
		"doctor_name": invoice.ledger.doctor.display_name,
		"doctor_specialty": invoice.ledger.doctor.specialty,
		"line_items": line_items,
		"subtotal": invoice.subtotal,
		"discount": invoice.discount,
		"tax": invoice.tax,
		"total": invoice.total,
	}


def _age_from_dob(dob):
	today = datetime.utcnow().date()
	return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _redirect_user_mgmt(status, message):
	query = urlencode({"status": status, "message": message})
	return redirect(f"/users/manage/?{query}")


def home(request):
	roles = set(request.user.groups.values_list("name", flat=True)) if request.user.is_authenticated else set()
	welcome_name = request.user.username if request.user.is_authenticated else ""
	if request.user.is_authenticated:
		base_name = (request.user.first_name or request.user.username or "").strip()
		if "Doctor" in roles:
			doctor_profile = getattr(request.user, "doctor_profile", None)
			suffix = ((doctor_profile.suffix if doctor_profile else "Dr") or "Dr").strip().rstrip(".")
			welcome_name = f"{suffix}.{base_name}" if base_name else f"{suffix}."
		else:
			welcome_name = base_name
	context = {
		"is_admin": "Admin" in roles,
		"is_doctor": "Doctor" in roles,
		"is_receptionist": "Receptionist" in roles,
		"is_pharmacist": "Pharmacist" in roles,
		"welcome_name": welcome_name,
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
@role_required("Doctor", "Admin")
def doctor_appointments_page(request):
	return render(request, "doctor_appointments.html")


@require_GET
@login_required
@role_required("Doctor", "Admin")
def doctor_consultation_page(request):
	return render(request, "doctor_consultation.html")


@require_GET
@login_required
@role_required("Doctor", "Admin")
def doctor_vitals_orders_page(request):
	return render(request, "doctor_vitals_orders.html")


@require_GET
@login_required
@role_required("Doctor", "Admin")
def doctor_prescription_page(request):
	return render(request, "doctor_prescription.html")


@require_GET
@login_required
@role_required("Doctor", "Admin")
def doctor_queue_page(request):
	return render(request, "doctor_queue.html")


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
			"opd_number": patient.opd_number,
			"age": _age_from_dob(patient.dob),
			"weight_kg": str(patient.weight_kg) if patient.weight_kg is not None else None,
			"known_history": patient.known_history,
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
			"opd_number": updated.opd_number,
			"age": _age_from_dob(updated.dob),
			"weight_kg": str(updated.weight_kg) if updated.weight_kg is not None else None,
			"phone": updated.phone,
		}
	)


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def patient_detail(request, patient_id):
	try:
		patient = Patient.objects.get(id=patient_id)
	except Patient.DoesNotExist:
		return JsonResponse({"error": "patient_not_found"}, status=404)

	return JsonResponse({
		"id": patient.id,
		"first_name": patient.first_name,
		"last_name": patient.last_name,
		"age": _age_from_dob(patient.dob),
		"weight_kg": str(patient.weight_kg) if patient.weight_kg is not None else None,
		"known_history": patient.known_history,
		"gender": patient.gender,
		"phone": patient.phone,
		"address_line1": patient.address_line1,
		"opd_number": patient.opd_number,
		"mrn": patient.mrn,
	})


@require_POST
@login_required
@role_required("Doctor", "Admin")
def patient_known_history_update(request, patient_id):
	try:
		patient = Patient.objects.get(id=patient_id)
	except Patient.DoesNotExist:
		return JsonResponse({"error": "patient_not_found"}, status=404)

	known_history = request.POST.get("known_history", "")
	patient.known_history = known_history
	patient.save(update_fields=["known_history"])

	return JsonResponse(
		{
			"status": "updated",
			"patient_id": patient.id,
			"known_history": patient.known_history,
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
			"weight_kg": str(patient.weight_kg) if patient.weight_kg is not None else None,
			"mrn": patient.mrn,
			"opd_history": [
				{
					"appointment_id": a.id,
					"opd_number": a.opd_number,
					"slot_date": str(a.slot_date),
					"doctor_id": a.doctor_id,
					"doctor_name": a.doctor.display_name,
					"start_time": a.start_time.strftime("%H:%M"),
					"visit_type": a.visit_type,
					"channel": a.channel,
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
@role_required("Receptionist", "Admin")
def appointment_book_form(request):
	return render(request, "appointment_book.html")


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def patient_edit_form(request):
	return render(request, "patient_edit.html")


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def doctor_schedule_form(request):
	return render(request, "doctor_schedule.html")


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def patient_reminder_form(request):
	return render(request, "patient_reminder.html")


@require_GET
@login_required
def user_profile_form(request):
	return render(request, "user_profile.html")


@require_GET
@login_required
def user_profile_get(request):
	user = request.user
	profile = user.profile if hasattr(user, 'profile') else None
	doctor_profile = getattr(user, "doctor_profile", None)
	
	roles = []
	if user.groups.filter(name__icontains="Doctor").exists():
		roles.append("Doctor")
	if user.groups.filter(name__icontains="Receptionist").exists():
		roles.append("Receptionist")
	if user.groups.filter(name__icontains="Pharmacist").exists():
		roles.append("Pharmacist")
	if user.is_staff:
		roles.append("Admin")
	
	return JsonResponse({
		"first_name": user.first_name,
		"last_name": user.last_name,
		"email": user.email,
		"phone": doctor_profile.phone if doctor_profile else (profile.phone if profile else ""),
		"reg_number": doctor_profile.reg_number if doctor_profile else "",
		"suffix": doctor_profile.suffix if doctor_profile else "Dr",
		"bio": profile.bio if profile else "",
		"department": profile.department if profile else "",
		"roles": roles,
	})


@require_POST
@login_required
def user_profile_update(request):
	try:
		data = json.loads(request.body)
		user = request.user
		
		# Update User model
		user.first_name = data.get("first_name", user.first_name)
		user.last_name = data.get("last_name", user.last_name)
		user.email = data.get("email", user.email)
		user.save()
		
		# Update or create UserProfile
		from .models import UserProfile
		profile, created = UserProfile.objects.get_or_create(user=user)
		profile.phone = data.get("phone", profile.phone)
		profile.bio = data.get("bio", profile.bio)
		profile.department = data.get("department", profile.department)
		profile.save()

		doctor_profile = getattr(user, "doctor_profile", None)
		if doctor_profile is not None:
			doctor_profile.phone = data.get("phone", doctor_profile.phone)
			doctor_profile.reg_number = data.get("reg_number", doctor_profile.reg_number)
			doctor_profile.suffix = data.get("suffix", doctor_profile.suffix or "Dr")
			doctor_profile.save(update_fields=["phone", "reg_number", "suffix"])
		
		return JsonResponse({"status": "ok", "message": "Profile updated successfully"})
	except Exception as e:
		audit_logger.error("profile_update_error", extra={"user": request.user.username, "error": str(e)})
		return JsonResponse({"error": str(e)}, status=400)


@require_GET
@login_required
@role_required("Receptionist", "Doctor", "Pharmacist", "Admin")
def patient_search(request):
	mrn = request.GET.get("mrn", "").strip()
	opd_number = request.GET.get("opd_number", "").strip()
	phone = request.GET.get("phone", "").strip()
	name = request.GET.get("name", "").strip()
	dob = request.GET.get("dob", "").strip()
	age_raw = request.GET.get("age", "").strip()
	age = None
	if age_raw:
		try:
			age = int(age_raw)
		except ValueError:
			return JsonResponse({"error": "invalid_age"}, status=400)

	patients = search_patients(mrn=mrn, phone=phone, name=name, dob=dob, age=age, opd_number=opd_number)
	items = [
		{
			"id": patient.id,
			"opd_number": patient.opd_number,
			"full_name": f"{patient.first_name} {patient.last_name}",
			"first_name": patient.first_name,
			"last_name": patient.last_name,
			"phone": patient.phone,
			"age": _age_from_dob(patient.dob),
			"weight_kg": str(patient.weight_kg) if patient.weight_kg is not None else None,
			"known_history": patient.known_history,
			"gender": patient.get_gender_display(),
			"address": patient.address_line1,
		}
		for patient in patients[:20]
	]

	query_type = "patient_opd_number" if opd_number else "mrn" if mrn else "phone" if phone else "name_age" if (name or age_raw) else "none"
	query_value = opd_number or mrn or phone or f"{name}|{age_raw or dob}"
	log_search(request.user.username, query_type, query_value, len(items))

	return JsonResponse({"items": items})


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def appointment_next_token(request):
	"""Return the next available token for a doctor on a given date."""
	doctor_id = request.GET.get("doctor_id", "").strip()
	slot_date = request.GET.get("slot_date", "").strip()
	if not doctor_id or not slot_date:
		return JsonResponse({"error": "doctor_id and slot_date are required"}, status=400)
	try:
		doctor = Doctor.objects.get(id=int(doctor_id))
	except (Doctor.DoesNotExist, ValueError):
		return JsonResponse({"error": "doctor_not_found"}, status=404)
	try:
		parsed_date = datetime.strptime(slot_date, "%Y-%m-%d").date()
	except ValueError:
		return JsonResponse({"error": "invalid_slot_date"}, status=400)
	booked_count = Appointment.objects.filter(
		doctor_id=doctor.id,
		slot_date=parsed_date,
	).exclude(status="CANCELLED").count()
	capacity = get_doctor_capacity_for_date(doctor, parsed_date)
	if booked_count >= capacity:
		return JsonResponse({
			"full": True,
			"booked_count": booked_count,
			"daily_capacity": capacity,
			"message": f"Doctor has reached daily capacity ({capacity} patients).",
		})
	return JsonResponse({
		"full": False,
		"next_token": booked_count + 1,
		"booked_count": booked_count,
		"daily_capacity": capacity,
	})


@require_GET
@login_required
@role_required("Receptionist", "Doctor", "Admin")
def doctor_list(request):
	slot_date = request.GET.get("slot_date", "").strip()
	start_time = request.GET.get("start_time", "").strip()
	apply_availability_filter = bool(slot_date or start_time)
	parsed_slot_date = None
	parsed_start_time = None

	if slot_date:
		try:
			parsed_slot_date = datetime.strptime(slot_date, "%Y-%m-%d").date()
		except ValueError:
			return JsonResponse({"error": "invalid_slot_date"}, status=400)

	if start_time:
		try:
			parsed_start_time = datetime.strptime(start_time, "%H:%M").time()
		except ValueError:
			return JsonResponse({"error": "invalid_start_time"}, status=400)

	if not apply_availability_filter:
		doctors = Doctor.objects.order_by("full_name")
	else:
		available_slots = DoctorSlot.objects.filter(status="AVAILABLE")
		if parsed_slot_date:
			available_slots = available_slots.filter(slot_date=parsed_slot_date)
		if parsed_start_time:
			available_slots = available_slots.filter(start_time=parsed_start_time)

		doctor_ids = available_slots.values_list("doctor_id", flat=True).distinct()
		doctors = Doctor.objects.filter(id__in=doctor_ids).order_by("full_name")

		if parsed_slot_date:
			eligible_doctors = []
			for doctor in doctors:
				active_count = Appointment.objects.filter(
					doctor_id=doctor.id,
					slot_date=parsed_slot_date,
				).exclude(status="CANCELLED").count()
				if active_count < get_doctor_capacity_for_date(doctor, parsed_slot_date):
					eligible_doctors.append(doctor.id)
			doctors = doctors.filter(id__in=eligible_doctors)
	items = [{"id": doctor.id, "name": doctor.display_name, "specialty": doctor.specialty} for doctor in doctors]
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
		if str(exc) in {"invalid_slot", "invalid_token", "doctor_daily_capacity_reached"}:
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
			"patient_opd_number": appointment.patient.opd_number,
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
@login_required(login_url="/login/")
@role_required("Doctor", "Admin")
def doctor_today_appointments(request):
	from django.utils import timezone
	from datetime import timedelta
	
	# Try to get the doctor associated with the logged-in user
	doctor = None
	
	# First, try direct user link
	try:
		doctor = Doctor.objects.get(user=request.user)
	except Doctor.DoesNotExist:
		pass
	
	# If no direct link, try matching by username (case-insensitive)
	if not doctor:
		try:
			doctor = Doctor.objects.get(full_name__icontains=request.user.username)
		except Doctor.DoesNotExist:
			pass
	
	# If still no match, try matching by first name
	if not doctor and request.user.first_name:
		try:
			doctor = Doctor.objects.get(full_name__icontains=request.user.first_name)
		except Doctor.DoesNotExist:
			pass
	
	if not doctor:
		# No doctor profile yet - return empty appointments gracefully
		return JsonResponse(
			{
				"doctor_id": None,
				"doctor_name": request.user.first_name or request.user.username,
				"date": str(timezone.localdate()),
				"latest_called_appointment_id": None,
				"appointments": [],
			}
		)
	
	# Get date based on date_type parameter (today or tomorrow)
	date_type = request.GET.get("date_type", "today")
	for_date = timezone.localdate()
	if date_type == "tomorrow":
		for_date = for_date + timedelta(days=1)

	sync_queue_for_day(doctor.id, for_date)
	queue_items = {
		item.appointment_id: item
		for item in QueueItem.objects.filter(doctor_id=doctor.id, slot_date=for_date)
	}
	latest_called = (
		QueueItem.objects
		.filter(doctor_id=doctor.id, slot_date=for_date, status="CALLED")
		.order_by("-called_at")
		.first()
	)
	
	appointments = doctor_appointments_for_day(doctor.id, for_date)
	return JsonResponse(
		{
			"doctor_id": doctor.id,
			"doctor_name": doctor.display_name,
			"date": str(for_date),
			"latest_called_appointment_id": latest_called.appointment_id if latest_called else None,
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
					"queue_token": queue_items[a.id].token_number if a.id in queue_items else None,
					"queue_status": queue_items[a.id].status if a.id in queue_items else "NOT_IN_QUEUE",
				}
				for a in appointments
			],
		}
	)


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def receptionist_today_appointments_board(request):
	from django.utils import timezone

	for_date = timezone.localdate()
	doctor_ids = list(
		Doctor.objects.filter(appointments__slot_date=for_date)
		.distinct()
		.values_list("id", flat=True)
	)
	for doctor_id in doctor_ids:
		sync_queue_for_day(doctor_id, for_date)

	queue_items = {
		item.appointment_id: item
		for item in QueueItem.objects.select_related("appointment").filter(slot_date=for_date)
	}
	latest_called = (
		QueueItem.objects
		.filter(slot_date=for_date, status="CALLED")
		.order_by("-called_at")
		.first()
	)

	appointments = (
		Appointment.objects
		.select_related("patient", "doctor")
		.filter(slot_date=for_date)
		.exclude(status="CANCELLED")
		.order_by("doctor__full_name", "start_time")
	)

	return JsonResponse(
		{
			"date": str(for_date),
			"latest_called_appointment_id": latest_called.appointment_id if latest_called else None,
			"appointments": [
				{
					"appointment_id": a.id,
					"doctor_id": a.doctor_id,
					"doctor_name": a.doctor.display_name,
					"patient_id": a.patient_id,
					"patient_name": f"{a.patient.first_name} {a.patient.last_name}",
					"mobile": a.patient.phone,
					"opd_number": a.opd_number,
					"start_time": a.start_time.strftime("%H:%M"),
					"status": a.status,
					"queue_token": queue_items[a.id].token_number if a.id in queue_items else None,
					"queue_status": queue_items[a.id].status if a.id in queue_items else "NOT_IN_QUEUE",
				}
				for a in appointments
			],
		}
	)


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def tomorrow_reminder_report_view(request):
	doctor_name = request.GET.get("doctor_name")
	doctor_id = None
	if doctor_name:
		try:
			doctor = Doctor.objects.get(full_name__icontains=doctor_name)
			doctor_id = doctor.id
		except Doctor.DoesNotExist:
			pass
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
					"doctor_name": a.doctor.display_name,
					"slot_time": a.start_time.strftime("%H:%M"),
				}
				for a in items
			],
		}
	)


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def tomorrow_reminder_report_pdf_download_view(request):
	doctor_name = (request.GET.get("doctor_name") or "").strip()
	doctor_id = None
	resolved_doctor_name = "All Doctors"
	if doctor_name:
		try:
			doctor = Doctor.objects.get(full_name__icontains=doctor_name)
			doctor_id = doctor.id
			resolved_doctor_name = doctor.display_name
		except Doctor.DoesNotExist:
			resolved_doctor_name = doctor_name

	target_date, items = tomorrow_reminder_report(doctor_id=doctor_id)

	lines = [
		"OPD Tomorrow Reminder Call List",
		f"Date: {target_date}",
		f"Doctor Filter: {resolved_doctor_name}",
		f"Total Appointments: {len(items)}",
		"",
	]

	if items:
		for idx, appointment in enumerate(items, start=1):
			patient_name = f"{appointment.patient.first_name} {appointment.patient.last_name}".strip()
			lines.extend(
				[
					f"{idx}. {patient_name}",
					f"   OPD Number: {appointment.opd_number or '-'}",
					f"   Mobile: {appointment.patient.phone or '-'}",
					f"   Doctor: {appointment.doctor.display_name}",
					f"   Slot Time: {appointment.start_time.strftime('%H:%M')}",
					"",
				]
			)
	else:
		lines.append("No appointments scheduled for tomorrow.")

	pdf_like_content = "\n".join(lines)
	response = HttpResponse(pdf_like_content, content_type="application/pdf")
	response["Content-Disposition"] = f'attachment; filename="tomorrow-reminder-{target_date}.pdf"'
	return response


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
		if str(exc) in {"invalid_transition", "invalid_slot", "invalid_token", "doctor_daily_capacity_reached"}:
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
			"clinic_name": _opd_clinic_name(),
			"clinic_address": _opd_clinic_address(),
			"create_form": UserCreateForm(),
			"assign_form": UserRoleAssignForm(),
			"message": request.GET.get("message", ""),
			"status": request.GET.get("status", ""),
		},
	)


@require_POST
@login_required
@role_required("Admin")
def clinic_settings_update(request):
	clinic_name = (request.POST.get("clinic_name") or "").strip()
	clinic_address = (request.POST.get("clinic_address") or "").strip()
	if not clinic_name:
		return _redirect_user_mgmt("error", "Clinic name is required.")
	settings = ClinicSettings.get_solo()
	settings.clinic_name = clinic_name
	settings.clinic_address = clinic_address
	settings.save(update_fields=["clinic_name", "clinic_address", "updated_at"])
	return _redirect_user_mgmt("success", "Clinic details updated successfully.")


@require_POST
@login_required
@role_required("Admin")
def user_create(request):
	form = UserCreateForm(request.POST)
	roles = sorted(ROLE_PERMISSION_MATRIX.keys())
	if not form.is_valid():
		return _redirect_user_mgmt("error", "User creation failed. Check input values.")

	role_name = (form.cleaned_data.get("role") or "").strip()
	if role_name and role_name not in roles:
		return _redirect_user_mgmt("error", "User creation failed. Check input values.")

	user = User.objects.create_user(
		username=form.cleaned_data["username"],
		password=form.cleaned_data["password"],
	)
	user.first_name = (form.cleaned_data.get("first_name") or "").strip()
	user.last_name = (form.cleaned_data.get("last_name") or "").strip()
	user.email = (form.cleaned_data.get("email") or "").strip()
	user.save(update_fields=["first_name", "last_name", "email"])

	group = None
	if role_name:
		group, _ = Group.objects.get_or_create(name=role_name)
		user.groups.set([group])

	if group and group.name == "Doctor":
		doctor_full_name = (form.cleaned_data.get("doctor_full_name") or "").strip()
		if not doctor_full_name:
			doctor_full_name = f"{user.first_name} {user.last_name}".strip() or user.username

		doctor_specialty = (form.cleaned_data.get("doctor_specialty") or "").strip()
		if not doctor_specialty:
			doctor_specialty = "General Medicine"

		doctor_capacity = form.cleaned_data.get("doctor_daily_patient_capacity") or 50

		Doctor.objects.update_or_create(
			user=user,
			defaults={
				"full_name": doctor_full_name,
				"suffix": (form.cleaned_data.get("doctor_suffix") or "Dr").strip() or "Dr",
				"specialty": doctor_specialty,
				"phone": (form.cleaned_data.get("doctor_phone") or "").strip(),
				"reg_number": (form.cleaned_data.get("doctor_reg_number") or "").strip(),
				"qualification": (form.cleaned_data.get("doctor_qualification") or "").strip(),
				"daily_patient_capacity": doctor_capacity,
			},
		)

	if group:
		return _redirect_user_mgmt("success", f"User {user.username} created with role {group.name}.")
	return _redirect_user_mgmt("success", f"User {user.username} created successfully.")


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
	
	# Auto-create a basic doctor profile if assigning Doctor role and profile doesn't exist
	if group.name == "Doctor":
		doctor_profile, created = Doctor.objects.get_or_create(
			user=user,
			defaults={
				"full_name": f"{user.first_name} {user.last_name}".strip() or user.username,
				"suffix": "Dr",
				"specialty": "General Medicine",
				"phone": "",
				"daily_patient_capacity": 50,
			},
		)
		if created:
			return _redirect_user_mgmt("success", f"Role for {user.username} updated to {group.name}. Doctor profile created.")
	
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
@role_required("Receptionist", "Doctor", "Admin")
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
@role_required("Doctor", "Receptionist", "Admin")
def queue_mark_called(request, appointment_id):
	try:
		queue_item = queue_mark_called_for_appointment(appointment_id, request.user.username)
	except Appointment.DoesNotExist:
		return JsonResponse({"error": "appointment_not_found"}, status=404)
	except QueueItem.DoesNotExist:
		return JsonResponse({"error": "queue_item_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) == "invalid_transition":
			return JsonResponse({"error": "invalid_transition"}, status=409)
		raise

	return JsonResponse(
		{
			"status": queue_item.status,
			"queue_item_id": queue_item.id,
			"appointment_id": queue_item.appointment_id,
			"token_number": queue_item.token_number,
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


@require_GET
@login_required
@role_required("Doctor", "Admin")
def consultation_context(request, appointment_id):
	try:
		appointment = Appointment.objects.select_related("patient", "doctor").get(id=appointment_id)
	except Appointment.DoesNotExist:
		return JsonResponse({"error": "appointment_not_found"}, status=404)

	patient = appointment.patient
	current_consultation = Consultation.objects.filter(appointment_id=appointment_id).first()
	latest_vitals = Vitals.objects.filter(patient_id=patient.id).order_by("-recorded_at").first()

	history_consultations = (
		Consultation.objects
		.select_related("doctor", "appointment")
		.filter(patient_id=patient.id)
		.exclude(appointment_id=appointment_id)
		.order_by("-created_at")[:5]
	)

	history = []
	for consultation in history_consultations:
		weight_kg = None
		if hasattr(consultation, "vitals") and consultation.vitals.weight_kg is not None:
			weight_kg = str(consultation.vitals.weight_kg)

		history.append(
			{
				"consultation_id": consultation.id,
				"appointment_id": consultation.appointment_id,
				"doctor_name": consultation.doctor.display_name,
				"slot_date": str(consultation.appointment.slot_date),
				"chief_complaint": consultation.chief_complaint,
				"diagnosis": consultation.diagnosis,
				"notes": consultation.notes,
				"weight_kg": weight_kg,
			}
		)

	last_prescription = (
		Prescription.objects
		.select_related("consultation", "doctor")
		.filter(patient_id=patient.id)
		.exclude(consultation__appointment_id=appointment_id)
		.order_by("-issued_at")
		.first()
	)

	last_prescription_payload = None
	if last_prescription:
		last_prescription_payload = {
			"prescription_id": last_prescription.id,
			"consultation_id": last_prescription.consultation_id,
			"rx_number": last_prescription.rx_number,
			"issued_at": last_prescription.issued_at.strftime("%d/%m/%Y %H:%M"),
			"doctor_name": last_prescription.doctor.display_name,
			"special_instructions": last_prescription.special_instructions,
			"items": last_prescription.items,
		}

	context_vitals = None
	if current_consultation and hasattr(current_consultation, "vitals"):
		vitals = current_consultation.vitals
		context_vitals = {
			"temperature_c": str(vitals.temperature_c) if vitals.temperature_c is not None else None,
			"pulse_bpm": vitals.pulse_bpm,
			"bp_systolic": vitals.bp_systolic,
			"bp_diastolic": vitals.bp_diastolic,
			"spo2_pct": vitals.spo2_pct,
			"weight_kg": str(vitals.weight_kg) if vitals.weight_kg is not None else None,
			"height_cm": str(vitals.height_cm) if vitals.height_cm is not None else None,
		}
	elif latest_vitals:
		context_vitals = {
			"temperature_c": str(latest_vitals.temperature_c) if latest_vitals.temperature_c is not None else None,
			"pulse_bpm": latest_vitals.pulse_bpm,
			"bp_systolic": latest_vitals.bp_systolic,
			"bp_diastolic": latest_vitals.bp_diastolic,
			"spo2_pct": latest_vitals.spo2_pct,
			"weight_kg": str(latest_vitals.weight_kg) if latest_vitals.weight_kg is not None else None,
			"height_cm": str(latest_vitals.height_cm) if latest_vitals.height_cm is not None else None,
		}

	return JsonResponse(
		{
			"appointment": {
				"appointment_id": appointment.id,
				"opd_number": appointment.opd_number,
				"doctor_id": appointment.doctor_id,
				"slot_date": str(appointment.slot_date),
				"doctor_name": appointment.doctor.display_name,
			},
			"patient": {
				"patient_id": patient.id,
				"opd_number": patient.opd_number,
				"full_name": f"{patient.first_name} {patient.last_name}",
				"age": _age_from_dob(patient.dob),
				"gender": patient.get_gender_display(),
				"phone": patient.phone,
				"weight_kg": str(latest_vitals.weight_kg) if latest_vitals and latest_vitals.weight_kg is not None else (str(patient.weight_kg) if patient.weight_kg is not None else None),
				"known_history": patient.known_history,
			},
			"current_consultation": {
				"consultation_id": current_consultation.id,
				"status": current_consultation.status,
				"chief_complaint": current_consultation.chief_complaint,
				"findings": current_consultation.findings,
				"diagnosis": current_consultation.diagnosis,
				"notes": current_consultation.notes,
				"follow_up_date": str(current_consultation.follow_up_date) if current_consultation.follow_up_date else None,
			} if current_consultation else None,
			"vitals": context_vitals,
			"previous_history": history,
			"last_prescription": last_prescription_payload,
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


@require_POST
@login_required
@role_required("Doctor", "Admin")
def prescription_update(request, consultation_id):
	import json
	try:
		payload = json.loads(request.body)
		if not isinstance(payload, dict):
			raise ValueError
	except (ValueError, KeyError):
		return JsonResponse({"error": "invalid_json"}, status=400)

	try:
		prescription = update_prescription(consultation_id, payload, request.user.username)
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
		status=200,
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
				"name": doctor.display_name,
				"specialty": doctor.specialty,
				"qualification": p.doctor_qualification,
				"reg_number": p.doctor_reg_number,
			},
			"clinic": {
				"name": p.clinic_name or _opd_clinic_name(),
				"address": p.clinic_address or _opd_clinic_address(),
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
def prescription_history_by_patient(request):
	name = request.GET.get("name", "").strip()
	phone = request.GET.get("phone", "").strip()

	if not name and not phone:
		return JsonResponse({"error": "name_or_phone_required"}, status=400)

	queryset = Prescription.objects.select_related("patient", "doctor", "consultation").order_by("-issued_at", "-id")

	if phone:
		queryset = queryset.filter(patient__phone__icontains=phone)

	if name:
		name_parts = [part for part in name.split(" ") if part]
		name_query = Q(patient__first_name__icontains=name) | Q(patient__last_name__icontains=name)
		if len(name_parts) >= 2:
			first_name = name_parts[0]
			last_name = " ".join(name_parts[1:])
			name_query = name_query | Q(patient__first_name__icontains=first_name, patient__last_name__icontains=last_name)
		queryset = queryset.filter(name_query)

	items = [
		{
			"prescription_id": p.id,
			"consultation_id": p.consultation_id,
			"rx_number": p.rx_number,
			"issued_at": p.issued_at.strftime("%d/%m/%Y %H:%M"),
			"patient_id": p.patient_id,
			"patient_name": f"{p.patient.first_name} {p.patient.last_name}",
			"mobile": p.patient.phone,
			"doctor_name": p.doctor.display_name,
			"diagnosis": p.consultation.diagnosis,
			"item_count": len(p.items or []),
		}
		for p in queryset[:200]
	]

	return JsonResponse({"count": len(items), "items": items})


@require_GET
@login_required
@role_required("Doctor", "Pharmacist", "Admin")
@xframe_options_sameorigin
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
		"auto_print": request.GET.get("print") == "1",
		"issued_at": p.issued_at,
		"validity_days": p.validity_days,
		"clinic_name": p.clinic_name or _opd_clinic_name(),
		"clinic_address": p.clinic_address or _opd_clinic_address(),
		"doctor_name": doctor.display_name,
		"doctor_specialty": doctor.specialty,
		"doctor_qualification": p.doctor_qualification,
		"doctor_reg_number": p.doctor_reg_number,
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


@require_POST
@login_required
@role_required("Doctor", "Admin")
def medical_order_create_for_patient(request, patient_id):
	form = MedicalOrderForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	try:
		order, consultation = create_medical_order_for_patient(
			patient_id=patient_id,
			order_type=form.cleaned_data["order_type"],
			description=form.cleaned_data["description"],
			actor_username=request.user.username,
		)
	except ValueError as exc:
		if str(exc) in {"finalized_consultation_not_found", "invalid_order_type", "consultation_not_finalized"}:
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	return JsonResponse(
		{
			"order_id": order.id,
			"consultation_id": consultation.id,
			"patient_id": consultation.patient_id,
			"patient_opd_number": consultation.patient.opd_number,
			"appointment_opd_number": consultation.appointment.opd_number,
			"order_type": order.order_type,
			"description": order.description,
			"status": order.status,
		},
		status=201,
	)


@require_GET
@login_required
@role_required("Doctor", "Pharmacist", "Admin")
def patient_medical_order_context(request, patient_id):
	try:
		patient = Patient.objects.get(id=patient_id)
	except Patient.DoesNotExist:
		return JsonResponse({"error": "patient_not_found"}, status=404)

	latest_consultation = (
		Consultation.objects.select_related("doctor", "appointment")
		.filter(patient_id=patient_id, status="FINALIZED")
		.order_by("-finalized_at", "-created_at")
		.first()
	)

	orders = (
		MedicalOrder.objects.select_related("consultation", "consultation__doctor")
		.filter(patient_id=patient_id)
		.order_by("-created_at", "-id")
	)

	return JsonResponse(
		{
			"patient": {
				"id": patient.id,
				"full_name": f"{patient.first_name} {patient.last_name}",
				"opd_number": patient.opd_number,
				"phone": patient.phone,
			},
			"latest_finalized_consultation": {
				"consultation_id": latest_consultation.id,
				"doctor_name": latest_consultation.doctor.display_name,
				"slot_date": str(latest_consultation.appointment.slot_date),
				"finalized_at": latest_consultation.finalized_at.strftime("%d/%m/%Y %H:%M") if latest_consultation.finalized_at else None,
				"diagnosis": latest_consultation.diagnosis,
				"appointment_opd_number": latest_consultation.appointment.opd_number,
			} if latest_consultation else None,
			"orders": [
				{
					"order_id": order.id,
					"consultation_id": order.consultation_id,
					"order_type": order.order_type,
					"description": order.description,
					"status": order.status,
					"doctor_name": order.consultation.doctor.display_name,
					"created_by": order.created_by,
					"created_at": order.created_at.strftime("%d/%m/%Y %H:%M"),
				}
				for order in orders[:100]
			],
		}
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


@login_required
@require_GET
@role_required("Receptionist", "Admin")
def billing_ledger_by_opd_get(request):
	opd_number = request.GET.get("opd_number", "").strip()
	if not opd_number:
		return JsonResponse({"error": "opd_number_required"}, status=400)

	ledger = (
		BillingLedger.objects.select_related("patient", "doctor")
		.prefetch_related("line_items")
		.filter(opd_number=opd_number)
		.first()
	)
	if ledger is None:
		return JsonResponse({"error": "ledger_not_found"}, status=404)

	return JsonResponse({"status": "success", "message": "ledger_fetched", "data": _billing_ledger_payload(ledger)})


@login_required
@require_POST
@role_required("Receptionist", "Admin")
def billing_ledger_by_opd_create(request):
	opd_number = request.POST.get("opd_number", "").strip()
	appointment_id_raw = request.POST.get("appointment_id", "").strip()
	appointment_id = None
	if appointment_id_raw:
		try:
			appointment_id = int(appointment_id_raw)
		except ValueError:
			return JsonResponse({"error": "invalid_appointment_id"}, status=400)

	try:
		ledger, created = create_or_get_active_billing_ledger(opd_number, request.user.username, appointment_id=appointment_id)
	except Appointment.DoesNotExist:
		return JsonResponse({"error": "appointment_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=400)

	ledger = BillingLedger.objects.select_related("patient", "doctor").prefetch_related("line_items").get(id=ledger.id)
	return JsonResponse(
		{
			"status": "success",
			"message": "ledger_created" if created else "ledger_reused",
			"data": _billing_ledger_payload(ledger),
		},
		status=201 if created else 200,
	)


@login_required
@require_POST
@role_required("Receptionist", "Admin")
def billing_ledger_add_line_item(request, ledger_id):
	line_type = request.POST.get("line_type", "").strip()
	amount = request.POST.get("amount", "").strip()
	description = request.POST.get("description", "").strip()
	source_order_id = request.POST.get("source_order_id", "").strip()
	if not line_type or not amount:
		return JsonResponse({"error": "line_type_and_amount_required"}, status=400)

	try:
		item = add_billing_line_item(
			ledger_id=ledger_id,
			line_type=line_type,
			amount=amount,
			actor_username=request.user.username,
			description=description,
			source_order_id=source_order_id,
		)
	except BillingLedger.DoesNotExist:
		return JsonResponse({"error": "ledger_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=400)

	return JsonResponse({"status": "success", "message": "line_item_added", "data": _billing_line_item_payload(item)}, status=201)


@login_required
@require_POST
@role_required("Receptionist", "Admin")
def billing_ledger_repeat_fee_decision(request, ledger_id):
	decision = request.POST.get("decision", "").strip().upper()
	reason = request.POST.get("reason", "").strip()
	amount = request.POST.get("amount", "").strip()
	amount_value = amount if amount else None

	try:
		ledger = set_repeat_fee_decision(
			ledger_id=ledger_id,
			decision=decision,
			actor_username=request.user.username,
			reason=reason,
			amount=amount_value,
		)
	except BillingLedger.DoesNotExist:
		return JsonResponse({"error": "ledger_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=400)

	ledger = BillingLedger.objects.select_related("patient", "doctor").prefetch_related("line_items").get(id=ledger.id)
	return JsonResponse({"status": "success", "message": "repeat_fee_decision_saved", "data": _billing_ledger_payload(ledger)})


@login_required
@require_POST
@role_required("Receptionist", "Admin")
def billing_ledger_finalize(request, ledger_id):
	tax = request.POST.get("tax", "0").strip() or "0"
	discount = request.POST.get("discount", "0").strip() or "0"
	try:
		ledger, invoice = finalize_billing_ledger(
			ledger_id=ledger_id,
			actor_username=request.user.username,
			tax=tax,
			discount=discount,
		)
	except BillingLedger.DoesNotExist:
		return JsonResponse({"error": "ledger_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=400)

	return JsonResponse(
		{
			"status": "success",
			"message": "ledger_finalized",
			"data": {
				"ledger_id": ledger.id,
				"ledger_status": ledger.status,
				"invoice_id": invoice.id,
				"bill_number": invoice.bill_number,
				"subtotal": str(invoice.subtotal),
				"discount": str(invoice.discount),
				"tax": str(invoice.tax),
				"total": str(invoice.total),
			},
		}
	)


@login_required
@require_GET
@role_required("Receptionist", "Admin")
def billing_invoice_get(request, invoice_id):
	try:
		invoice = BillingInvoice.objects.select_related("ledger", "ledger__patient", "ledger__doctor").get(id=invoice_id)
	except BillingInvoice.DoesNotExist:
		return JsonResponse({"error": "invoice_not_found"}, status=404)

	line_items = BillingLineItem.objects.filter(ledger_id=invoice.ledger_id).order_by("created_at")
	return JsonResponse(
		{
			"status": "success",
			"message": "invoice_fetched",
			"data": {
				"clinic_name": _opd_clinic_name(),
				"clinic_address": _opd_clinic_address(),
				"invoice_id": invoice.id,
				"bill_number": invoice.bill_number,
				"created_at": invoice.created_at.isoformat(),
				"opd_number": invoice.ledger.opd_number,
				"visit_date": str(invoice.ledger.visit_date),
				"patient": {
					"patient_id": invoice.ledger.patient_id,
					"name": f"{invoice.ledger.patient.first_name} {invoice.ledger.patient.last_name}".strip(),
					"phone": invoice.ledger.patient.phone,
				},
				"doctor": {
					"doctor_id": invoice.ledger.doctor_id,
					"name": invoice.ledger.doctor.display_name,
					"specialty": invoice.ledger.doctor.specialty,
				},
				"line_items": [_billing_line_item_payload(item) for item in line_items],
				"totals": {
					"subtotal": str(invoice.subtotal),
					"discount": str(invoice.discount),
					"tax": str(invoice.tax),
					"total": str(invoice.total),
				},
				"print_url": f"/billing/invoice/{invoice.id}/print/",
				"pdf_download_url": f"/api/billing/invoice/{invoice.id}/pdf/",
			},
		}
	)


@login_required
@require_GET
@role_required("Receptionist", "Admin")
@xframe_options_sameorigin
def billing_invoice_print(request, invoice_id):
	try:
		invoice = BillingInvoice.objects.select_related("ledger", "ledger__patient", "ledger__doctor").get(id=invoice_id)
	except BillingInvoice.DoesNotExist:
		return JsonResponse({"error": "invoice_not_found"}, status=404)

	context = _invoice_print_context(invoice, auto_print=request.GET.get("print") == "1")
	return render(request, "billing_invoice_print.html", context)


@login_required
@require_GET
@role_required("Receptionist", "Admin")
def billing_invoice_pdf_download(request, invoice_id):
	try:
		invoice = BillingInvoice.objects.select_related("ledger", "ledger__patient", "ledger__doctor").get(id=invoice_id)
	except BillingInvoice.DoesNotExist:
		return JsonResponse({"error": "invoice_not_found"}, status=404)

	line_items = BillingLineItem.objects.filter(ledger_id=invoice.ledger_id).order_by("created_at")
	lines = [
		"OPD Billing Invoice",
		f"Clinic: {_opd_clinic_name()}",
		f"Clinic Address: {_opd_clinic_address() or '-'}",
		f"Bill Number: {invoice.bill_number}",
		f"Invoice Date: {invoice.created_at.strftime('%Y-%m-%d %H:%M')}",
		f"OPD Number: {invoice.ledger.opd_number}",
		f"Visit Date: {invoice.ledger.visit_date}",
		f"Patient: {invoice.ledger.patient.first_name} {invoice.ledger.patient.last_name}".strip(),
		f"Mobile: {invoice.ledger.patient.phone or '-'}",
		f"Doctor: {invoice.ledger.doctor.display_name}",
		"",
		"Line Items:",
	]
	for idx, item in enumerate(line_items, start=1):
		lines.append(f"{idx}. {item.line_type} | {item.description or '-'} | Amount: {item.amount}")
	lines.extend(
		[
			"",
			f"Subtotal: {invoice.subtotal}",
			f"Discount: {invoice.discount}",
			f"Tax: {invoice.tax}",
			f"Total: {invoice.total}",
		]
	)
	payload = "\n".join(lines)

	response = HttpResponse(payload, content_type="application/pdf")
	response["Content-Disposition"] = f'attachment; filename="invoice-{invoice.bill_number}.pdf"'
	return response


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
