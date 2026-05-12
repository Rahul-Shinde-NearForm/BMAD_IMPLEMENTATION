import json
import logging
import os
import re
from urllib.parse import quote_plus
from django.db import IntegrityError
from urllib.parse import urlencode
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.management import call_command
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db import connections
from django.db.models import Q, Sum
from django.db.utils import OperationalError
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .forms import (
	AddEmergencyPatientForm,
	AppointmentBookForm,
	AppointmentCancelForm,
	DoctorEmergencyDayRescheduleForm,
	AppointmentRescheduleForm,
	ConsultationAmendForm,
	ConsultationDraftForm,
	MedicalOrderForm,
	PatientRegistrationForm,
	PauseCurrentConsultationForm,
	ReceptionEmergencyRescheduleDecisionForm,
	PatientUpdateForm,
	QueueBoardForm,
	QueueCallNextForm,
	ScheduleUpsertForm,
	UserCreateForm,
	UserRoleAssignForm,
	VitalsForm,
)
from .models import Appointment, BillingHandoff, BillingInvoice, BillingLedger, BillingLineItem, ClinicSettings, Consultation, Doctor, DoctorDayRescheduleRequest, DoctorSlot, IncidentRecord, MedicalOrder, Medicine, Patient, Prescription, QueueItem, ReportExport, Vitals
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
	add_emergency_patient,
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
	pause_current_consultation,
	create_billing_handoff,
	create_or_get_active_billing_ledger,
	get_relevant_billing_ledger_for_opd,
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
	trigger_doctor_day_unavailable,
	yesterday_missed_report,
	list_pending_day_reschedule_requests,
	decide_day_reschedule_request,
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
		"total_case_amount": str(item.total_case_amount) if item.total_case_amount else None,
		"recovery_stage_percent": item.recovery_stage_percent,
		"sitting_number": item.sitting_number,
		"total_sittings": item.total_sittings,
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
			"recovered_amount": str(ledger.invoice.recovered_amount),
			"recovered_percentage": ledger.invoice.recovered_percentage,
			"created_at": ledger.invoice.created_at.isoformat(),
		} if hasattr(ledger, "invoice") else None,
	}


def _opd_clinic_name():
	return ClinicSettings.get_solo().clinic_name


def _opd_clinic_address():
	return ClinicSettings.get_solo().clinic_address


def _patient_display_name(patient):
	return patient.titled_full_name


def _format_invoice_amount(value):
	amount = Decimal(str(value or 0))
	return f"{amount:.2f}"


def _invoice_current_total(invoice):
	"""
	For FOLLOW_UP_RCT invoices whose previous bill is fully paid, return the
	sum of only the *current-visit* line items (i.e. items added after the
	cloned ones).  For all other invoices, return invoice.total unchanged.
	"""
	if invoice.ledger.visit_type != "FOLLOW_UP_RCT":
		return invoice.total

	prev_invoice = (
		BillingInvoice.objects
		.select_related("ledger")
		.filter(ledger__patient_id=invoice.ledger.patient_id, created_at__lt=invoice.created_at)
		.exclude(id=invoice.id)
		.order_by("-created_at")
		.first()
	)
	if not prev_invoice or prev_invoice.payment_status != "DONE":
		return invoice.total

	n_cloned = BillingLineItem.objects.filter(ledger_id=prev_invoice.ledger_id).count()
	all_items = list(BillingLineItem.objects.filter(ledger_id=invoice.ledger_id).order_by("created_at"))
	current_items = all_items[n_cloned:]
	return sum((item.amount or Decimal("0")) for item in current_items)


def _invoice_print_context(invoice, auto_print=False, previous_bill_no="", previous_visit_date="", previous_payment_status="", previous_invoice_id=None):
	all_line_items = list(BillingLineItem.objects.filter(ledger_id=invoice.ledger_id).order_by("created_at"))
	previous_payment_status_normalized = (previous_payment_status or "").strip().upper()

	# Auto-detect previous invoice for FOLLOW_UP_RCT visits when not explicitly provided
	if not previous_invoice_id and invoice.ledger.visit_type == "FOLLOW_UP_RCT":
		auto_prev = (
			BillingInvoice.objects
			.select_related("ledger")
			.filter(ledger__patient_id=invoice.ledger.patient_id, created_at__lt=invoice.created_at)
			.exclude(id=invoice.id)
			.order_by("-created_at")
			.first()
		)
		if auto_prev:
			previous_invoice_id = auto_prev.id
			if not previous_bill_no:
				previous_bill_no = auto_prev.bill_number
			if not previous_visit_date:
				previous_visit_date = str(auto_prev.ledger.visit_date)
			if not previous_payment_status_normalized:
				previous_payment_status_normalized = auto_prev.payment_status

	previous_line_items_display = []
	if previous_invoice_id:
		try:
			prev_invoice = BillingInvoice.objects.select_related("ledger").get(id=previous_invoice_id)
			prev_items = BillingLineItem.objects.filter(ledger_id=prev_invoice.ledger_id).order_by("created_at")
			previous_line_items_display = [
				{
					"line_type_display": item.get_line_type_display(),
					"description": item.description or "-",
					"amount": _format_invoice_amount(item.amount),
				}
				for item in prev_items
			]
			# Current items = skip first N cloned items (N = count of previous invoice items)
			n_cloned = prev_items.count()
			current_items = all_line_items[n_cloned:]
		except BillingInvoice.DoesNotExist:
			current_items = all_line_items
	else:
		current_items = all_line_items

	line_items_display = [
		{
			"line_type_display": item.get_line_type_display(),
			"description": item.description or "-",
			"amount": _format_invoice_amount(item.amount),
		}
		for item in current_items
	]

	# For follow-up RCT prints with a settled previous bill, show totals only for current visit items.
	if previous_line_items_display and previous_payment_status_normalized == "DONE":
		current_subtotal_amount = sum((item.amount or Decimal("0")) for item in current_items)
		print_subtotal = current_subtotal_amount
		print_discount = Decimal("0")
		print_tax = Decimal("0")
		print_total = current_subtotal_amount
	else:
		print_subtotal = invoice.subtotal
		print_discount = invoice.discount
		print_tax = invoice.tax
		print_total = invoice.total

	clinic_settings = ClinicSettings.get_solo()
	return {
		"auto_print": auto_print,
		"previous_bill_no": (previous_bill_no or "").strip(),
		"previous_visit_date": (previous_visit_date or "").strip(),
		"previous_payment_status": previous_payment_status_normalized,
		"previous_line_items_display": previous_line_items_display,
		"clinic_name": _opd_clinic_name(),
		"clinic_address": _opd_clinic_address(),
		"clinic_phone": clinic_settings.clinic_phone,
		"clinic_mob": clinic_settings.clinic_mob,
		"invoice_id": invoice.id,
		"bill_number": invoice.bill_number,
		"created_at": invoice.created_at,
		"opd_number": invoice.ledger.opd_number,
		"visit_date": invoice.ledger.visit_date,
		"patient_name": _patient_display_name(invoice.ledger.patient),
		"patient_phone": invoice.ledger.patient.phone,
		"doctor_name": invoice.ledger.doctor.display_name,
		"doctor_specialty": invoice.ledger.doctor.specialty,
		"line_items_display": line_items_display,
		"subtotal": _format_invoice_amount(print_subtotal),
		"discount": _format_invoice_amount(print_discount),
		"tax": _format_invoice_amount(print_tax),
		"total": _format_invoice_amount(print_total),
	}


def _age_from_dob(dob):
	today = datetime.utcnow().date()
	return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _redirect_user_mgmt(status, message):
	query = urlencode({"status": status, "message": message})
	return redirect(f"/users/manage/?{query}")


def _normalize_doctor_name(value):
	text = (value or "").strip().lower()
	text = re.sub(r"^dr\.?\s+", "", text)
	return text


def _resolve_doctor_scope_for_user(user):
	primary = getattr(user, "doctor_profile", None)
	target_exact = set()
	target_contains = set()

	if primary:
		target_exact.add(_normalize_doctor_name(primary.full_name))
	if user.first_name:
		target_contains.add(_normalize_doctor_name(user.first_name))
	if user.username:
		target_contains.add(_normalize_doctor_name(user.username))

	target_exact = {t for t in target_exact if t}
	target_contains = {t for t in target_contains if t}

	matched = []
	for doctor in Doctor.objects.all().order_by("id"):
		normalized = _normalize_doctor_name(doctor.full_name)
		if target_exact and normalized in target_exact:
			matched.append(doctor)
			continue
		if any(len(token) >= 3 and token in normalized for token in target_contains):
			matched.append(doctor)

	if primary and primary.id not in [d.id for d in matched]:
		matched.insert(0, primary)

	if not matched:
		return None, []

	if primary:
		resolved_primary = primary
	else:
		resolved_primary = matched[0]

	ids = []
	seen = set()
	for doctor in matched:
		if doctor.id in seen:
			continue
		seen.add(doctor.id)
		ids.append(doctor.id)

	return resolved_primary, ids


def home(request):
	roles = set(request.user.groups.values_list("name", flat=True)) if request.user.is_authenticated else set()
	welcome_name = request.user.username if request.user.is_authenticated else ""
	clinic_name = "OPD Clinic"
	if request.user.is_authenticated:
		base_name = (request.user.first_name or request.user.username or "").strip()
		if "Doctor" in roles:
			doctor_profile = getattr(request.user, "doctor_profile", None)
			suffix = ((doctor_profile.suffix if doctor_profile else "Dr") or "Dr").strip().rstrip(".")
			welcome_name = f"{suffix}.{base_name}" if base_name else f"{suffix}."
		else:
			welcome_name = base_name
		try:
			clinic_name = _opd_clinic_name() or "OPD Clinic"
		except Exception:
			clinic_name = "OPD Clinic"
	context = {
		"is_admin": "Admin" in roles,
		"is_doctor": "Doctor" in roles,
		"is_receptionist": "Receptionist" in roles,
		"is_pharmacist": "Pharmacist" in roles,
		"welcome_name": welcome_name,
		"clinic_name": clinic_name,
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
@role_required("Receptionist", "Doctor", "Admin")
def appointments_stats(request):
	from datetime import datetime, timedelta
	from django.db.models import Count, Sum
	from django.db.models.functions import ExtractMonth
	
	# Get year and month from query params, default to today
	today = datetime.now().date()
	year = int(request.GET.get("year", today.year))
	month = int(request.GET.get("month", today.month))
	roles = set(request.user.groups.values_list("name", flat=True))

	# Doctors should only see their own appointment statistics.
	doctor_filter = {}
	if "Doctor" in roles and "Admin" not in roles and "Receptionist" not in roles:
		_, doctor_ids = _resolve_doctor_scope_for_user(request.user)
		if not doctor_ids:
			return JsonResponse({
				"year": year,
				"month": month,
				"daywise": {},
				"monthwise": {},
				"revenue_daywise": {},
				"revenue_monthwise": {},
			})
		doctor_filter = {"doctor_id__in": doctor_ids}

	billing_doctor_filter = {}
	if "doctor_id__in" in doctor_filter:
		billing_doctor_filter = {"ledger__doctor_id__in": doctor_filter["doctor_id__in"]}
	
	# Daywise counts for the specified month
	start_of_month = datetime(year, month, 1).date()
	if month == 12:
		end_of_month = datetime(year + 1, 1, 1).date() - timedelta(days=1)
	else:
		end_of_month = datetime(year, month + 1, 1).date() - timedelta(days=1)
	
	active_statuses = ["BOOKED", "RESCHEDULED", "COMPLETED"]

	# Daywise counting rule:
	# - past days: only successfully completed appointments
	# - today/future days: all scheduled+completed appointments (excluding cancelled)
	daywise_past = Appointment.objects.filter(
		slot_date__gte=start_of_month,
		slot_date__lte=end_of_month,
		slot_date__lt=today,
		status="COMPLETED",
		**doctor_filter,
	).values("slot_date").annotate(count=Count("id")).order_by("slot_date")

	daywise_future_start = max(start_of_month, today)
	daywise_current_and_future = Appointment.objects.filter(
		slot_date__gte=daywise_future_start,
		slot_date__lte=end_of_month,
		status__in=active_statuses,
		**doctor_filter,
	).values("slot_date").annotate(count=Count("id")).order_by("slot_date")

	daywise_dict = {}
	for item in daywise_past:
		daywise_dict[str(item["slot_date"])] = item["count"]
	for item in daywise_current_and_future:
		key = str(item["slot_date"])
		daywise_dict[key] = daywise_dict.get(key, 0) + item["count"]

	# Monthwise uses the same day rule aggregated by month.
	monthwise_past = Appointment.objects.filter(
		slot_date__year=year,
		slot_date__lt=today,
		status="COMPLETED",
		**doctor_filter,
	).annotate(month=ExtractMonth("slot_date")).values("month").annotate(count=Count("id")).order_by("month")

	monthwise_current_and_future = Appointment.objects.filter(
		slot_date__year=year,
		slot_date__gte=today,
		status__in=active_statuses,
		**doctor_filter,
	).annotate(month=ExtractMonth("slot_date")).values("month").annotate(count=Count("id")).order_by("month")

	monthwise_dict = {}
	for item in monthwise_past:
		month_key = int(item["month"])
		monthwise_dict[month_key] = item["count"]
	for item in monthwise_current_and_future:
		month_key = int(item["month"])
		monthwise_dict[month_key] = monthwise_dict.get(month_key, 0) + item["count"]

	revenue_daywise = BillingInvoice.objects.filter(
		ledger__visit_date__gte=start_of_month,
		ledger__visit_date__lte=end_of_month,
		**billing_doctor_filter,
	).values("ledger__visit_date").annotate(total_revenue=Sum("total")).order_by("ledger__visit_date")
	revenue_daywise_dict = {
		str(item["ledger__visit_date"]): f"{(item['total_revenue'] or 0):.2f}"
		for item in revenue_daywise
	}

	revenue_monthwise = BillingInvoice.objects.filter(
		ledger__visit_date__year=year,
		**billing_doctor_filter,
	).annotate(month=ExtractMonth("ledger__visit_date")).values("month").annotate(total_revenue=Sum("total")).order_by("month")
	revenue_monthwise_dict = {
		int(item["month"]): f"{(item['total_revenue'] or 0):.2f}"
		for item in revenue_monthwise
	}
	
	return JsonResponse({
		"year": year,
		"month": month,
		"daywise": daywise_dict,
		"monthwise": monthwise_dict,
		"revenue_daywise": revenue_daywise_dict,
		"revenue_monthwise": revenue_monthwise_dict,
	})


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


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def doctor_opd_fee_update(request):
	doctor_id = request.POST.get("doctor_id", "").strip()
	opd_new_patient_fee = request.POST.get("opd_new_patient_fee", "").strip()
	opd_existing_patient_fee = request.POST.get("opd_existing_patient_fee", "").strip()

	if not doctor_id:
		return JsonResponse({"error": "doctor_id_required"}, status=400)

	try:
		doctor = Doctor.objects.get(id=int(doctor_id))
	except (Doctor.DoesNotExist, ValueError):
		return JsonResponse({"error": "doctor_not_found"}, status=404)

	try:
		from decimal import Decimal, InvalidOperation
		doctor.opd_new_patient_fee = Decimal(opd_new_patient_fee)
		doctor.opd_existing_patient_fee = Decimal(opd_existing_patient_fee)
	except (InvalidOperation, ValueError):
		return JsonResponse({"error": "invalid_fee_amount"}, status=400)

	doctor.save(update_fields=["opd_new_patient_fee", "opd_existing_patient_fee"])

	return JsonResponse(
		{
			"status": "ok",
			"message": "opd_fee_updated",
			"data": {
				"doctor_id": doctor.id,
				"doctor_name": doctor.display_name,
				"opd_new_patient_fee": str(doctor.opd_new_patient_fee),
				"opd_existing_patient_fee": str(doctor.opd_existing_patient_fee),
			},
		}
	)


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
	try:
		clinic_name = _opd_clinic_name() or "OPD Clinic"
	except Exception:
		clinic_name = "OPD Clinic"
	
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
		"clinic_name": clinic_name,
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
	available_slots_count = DoctorSlot.objects.filter(
		doctor_id=doctor.id,
		slot_date=parsed_date,
		status="AVAILABLE",
	).count()
	if available_slots_count == 0:
		return JsonResponse({
			"full": True,
			"booked_count": booked_count,
			"daily_capacity": capacity,
			"message": f"Doctor is not available on this date. No slots have been set up.",
			"no_slots": True,
		})
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
	items = []
	seen = set()
	for doctor in doctors:
		key = (doctor.display_name.strip().lower(), (doctor.specialty or "").strip().lower())
		if key in seen:
			continue
		seen.add(key)
		items.append({
			"id": doctor.id,
			"name": doctor.display_name,
			"specialty": doctor.specialty,
			"opd_new_patient_fee": str(doctor.opd_new_patient_fee),
			"opd_existing_patient_fee": str(doctor.opd_existing_patient_fee),
		})
	response = JsonResponse({"items": items})
	response["Cache-Control"] = "no-store"
	return response


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

	doctor, doctor_ids = _resolve_doctor_scope_for_user(request.user)
	if not doctor or not doctor_ids:
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

	for doctor_id in doctor_ids:
		sync_queue_for_day(doctor_id, for_date)
	queue_items = {
		item.appointment_id: item
		for item in QueueItem.objects.filter(doctor_id__in=doctor_ids, slot_date=for_date)
	}
	latest_called = (
		QueueItem.objects
		.filter(doctor_id__in=doctor_ids, slot_date=for_date, status="CALLED")
		.order_by("-called_at")
		.first()
	)
	
	appointments = (
		Appointment.objects
		.select_related("patient", "doctor")
		.filter(doctor_id__in=doctor_ids, slot_date=for_date)
		.exclude(status="CANCELLED")
		.order_by("start_time")
	)
	appointments = list(appointments)
	appointment_ids = [a.id for a in appointments]
	invoice_rows = (
		BillingInvoice.objects
		.filter(ledger__appointment_id__in=appointment_ids)
		.values(
			"ledger__appointment_id",
			"payment_status",
			"total",
			"recovered_amount",
			"recovered_percentage",
		)
		.order_by("-created_at")
	)
	payment_by_appointment = {}
	for row in invoice_rows:
		appointment_id = row.get("ledger__appointment_id")
		if appointment_id not in payment_by_appointment:
			payment_by_appointment[appointment_id] = {
				"status": row.get("payment_status") or "PENDING",
				"recovered_percentage": int(row.get("recovered_percentage") or 0),
				"recovered_amount": row.get("recovered_amount") or Decimal("0"),
				"total": row.get("total") or Decimal("0"),
			}

	# Fetch RCT recovery information from billing line items
	rct_info_by_appointment = {}
	line_items = (
		BillingLineItem.objects
		.filter(ledger__appointment_id__in=appointment_ids, total_case_amount__isnull=False)
		.values(
			"ledger__appointment_id",
			"total_case_amount",
			"recovery_stage_percent",
			"sitting_number",
			"total_sittings",
			"amount",
		)
		.order_by("ledger__appointment_id", "-recovery_stage_percent")
	)
	for line_item in line_items:
		appointment_id = line_item.get("ledger__appointment_id")
		if appointment_id not in rct_info_by_appointment:
			rct_info_by_appointment[appointment_id] = {
				"total_case_amount": str(line_item.get("total_case_amount") or Decimal("0")),
				"recovery_stages": [],
				"total_recovered_percentage": 0,
				"total_recovered_amount": Decimal("0"),
				"opd_fee_amount": Decimal("0"),
			}
		stage_info = {
			"recovery_percent": line_item.get("recovery_stage_percent"),
			"sitting_number": line_item.get("sitting_number"),
			"total_sittings": line_item.get("total_sittings"),
			"amount": str(line_item.get("amount") or Decimal("0")),
		}
		rct_info_by_appointment[appointment_id]["recovery_stages"].append(stage_info)
		rct_info_by_appointment[appointment_id]["total_recovered_percentage"] = max(
			rct_info_by_appointment[appointment_id]["total_recovered_percentage"],
			line_item.get("recovery_stage_percent") or 0,
		)
		rct_info_by_appointment[appointment_id]["total_recovered_amount"] += Decimal(str(line_item.get("amount") or 0))

	# Fetch OPD fee amounts for RCT cases
	opd_fees = (
		BillingLineItem.objects
		.filter(ledger__appointment_id__in=appointment_ids, line_type__in=["OPD_NEW_FEE", "OPD_REPEAT_FEE"])
		.values("ledger__appointment_id")
		.annotate(total_opd=Sum("amount"))
	)
	opd_by_appointment = {row["ledger__appointment_id"]: row["total_opd"] or Decimal("0") for row in opd_fees}
	
	# Update RCT info with OPD fee
	for appointment_id in rct_info_by_appointment:
		rct_info_by_appointment[appointment_id]["opd_fee_amount"] = str(opd_by_appointment.get(appointment_id, Decimal("0")))

	def _payment_status_display(raw_status, recovered_percentage=0):
		if raw_status == "DONE":
			return "Done"
		if raw_status == "PENDING":
			if recovered_percentage > 0:
				return f"Partial ({recovered_percentage}% recovered)"
			return "Pending"
		return "Not Generated"

	return JsonResponse(
		{
			"doctor_id": doctor.id,
			"doctor_name": doctor.display_name,
			"date": str(for_date),
			"latest_called_appointment_id": latest_called.appointment_id if latest_called else None,
			"appointments": [
				{
					"appointment_id": a.id,
					"doctor_id": a.doctor_id,
					"opd_number": a.opd_number,
					"patient_id": a.patient_id,
					"patient_name": _patient_display_name(a.patient),
					"mobile": a.patient.phone,
					"start_time": a.start_time.strftime("%H:%M"),
					"end_time": a.end_time.strftime("%H:%M"),
					"status": a.status,
					"is_emergency": bool(a.is_emergency),
					"queue_token": queue_items[a.id].token_number if a.id in queue_items else None,
					"queue_status": queue_items[a.id].status if a.id in queue_items else "NOT_IN_QUEUE",
					"payment_status": payment_by_appointment.get(a.id, {}).get("status", "NOT_GENERATED"),
					"payment_status_display": _payment_status_display(
						payment_by_appointment.get(a.id, {}).get("status", "NOT_GENERATED"),
						payment_by_appointment.get(a.id, {}).get("recovered_percentage", 0),
					),
					"payment_recovered_percentage": payment_by_appointment.get(a.id, {}).get("recovered_percentage", 0),
					"payment_recovered_amount": str(payment_by_appointment.get(a.id, {}).get("recovered_amount", Decimal("0"))),
					"payment_pending_amount": str(
						max(
							Decimal("0"),
							(payment_by_appointment.get(a.id, {}).get("total", Decimal("0")) or Decimal("0"))
							- (payment_by_appointment.get(a.id, {}).get("recovered_amount", Decimal("0")) or Decimal("0")),
						)
					),
					"rct_recovery_info": rct_info_by_appointment.get(a.id),
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
					"is_emergency": bool(a.is_emergency),
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

	def _reminder_status_meta(appointment):
		latest_reschedule_reason = ""
		for event in reversed(list(appointment.events.all())):
			if event.action == "RESCHEDULE":
				latest_reschedule_reason = event.reason or ""
				break
		if latest_reschedule_reason.startswith("doctor_unavailable:"):
			return "Doctor requested to postpone", True
		return appointment.get_status_display(), False

	return JsonResponse(
		{
			"date": str(target_date),
			"count": len(items),
			"patients": [
				{
					"appointment_id": a.id,
					"patient_id": a.patient_id,
					"doctor_id": a.doctor_id,
					"opd_number": a.opd_number,
					"patient_name": _patient_display_name(a.patient),
					"mobile": a.patient.phone,
					"doctor_name": a.doctor.display_name,
					"slot_time": a.start_time.strftime("%H:%M"),
					"status_label": status_label,
					"appointment_status": a.status,
					"is_doctor_postponed": is_doctor_postponed,
				}
				for a in items
				for status_label, is_doctor_postponed in [_reminder_status_meta(a)]
			],
		}
	)


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def yesterday_missed_report_view(request):
	doctor_name = request.GET.get("doctor_name")
	doctor_id = None
	if doctor_name:
		try:
			doctor = Doctor.objects.get(full_name__icontains=doctor_name)
			doctor_id = doctor.id
		except Doctor.DoesNotExist:
			pass

	target_date, items = yesterday_missed_report(doctor_id=doctor_id)
	return JsonResponse(
		{
			"date": str(target_date),
			"count": len(items),
			"patients": [
				{
					"appointment_id": q.appointment_id,
					"patient_id": q.appointment.patient_id,
					"doctor_id": q.appointment.doctor_id,
					"opd_number": q.appointment.opd_number,
					"patient_name": _patient_display_name(q.appointment.patient),
					"mobile": q.appointment.patient.phone,
					"doctor_name": q.appointment.doctor.display_name,
					"slot_time": q.appointment.start_time.strftime("%H:%M"),
					"queue_status": q.status,
				}
				for q in items
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


@require_POST
@login_required
@role_required("Doctor", "Receptionist", "Admin")
def doctor_day_unavailable_reschedule(request):
	form = DoctorEmergencyDayRescheduleForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	source_date = form.cleaned_data.get("source_date") or timezone.localdate()
	reason = form.cleaned_data.get("reason") or "doctor_emergency_unavailable"

	if request.user.groups.filter(name="Admin").exists() or request.user.groups.filter(name="Receptionist").exists():
		doctor_id_raw = (request.POST.get("doctor_id") or "").strip()
		if not doctor_id_raw:
			return JsonResponse({"error": "doctor_id_required"}, status=400)
		try:
			doctor_id = int(doctor_id_raw)
		except ValueError:
			return JsonResponse({"error": "invalid_doctor_id"}, status=400)
	else:
		doctor, doctor_ids = _resolve_doctor_scope_for_user(request.user)
		if not doctor or not doctor_ids:
			return JsonResponse({"error": "doctor_profile_not_found"}, status=404)
		doctor_id_raw = (request.POST.get("doctor_id") or "").strip()
		if doctor_id_raw:
			try:
				doctor_id = int(doctor_id_raw)
			except ValueError:
				return JsonResponse({"error": "invalid_doctor_id"}, status=400)
			if doctor_id not in doctor_ids:
				return JsonResponse({"error": "doctor_not_in_scope"}, status=403)
		else:
			doctor_id = doctor.id

		# If selected doctor has no active appointments today, fall back to the only scoped
		# doctor that actually has active appointments. This handles ambiguous username/name
		# mappings while keeping doctor access scoped safely.
		active_scoped_ids = list(
			Appointment.objects.filter(
				doctor_id__in=doctor_ids,
				slot_date=source_date,
				status__in=["BOOKED", "RESCHEDULED"],
			)
			.values_list("doctor_id", flat=True)
			.distinct()
		)
		if doctor_id not in active_scoped_ids and len(active_scoped_ids) == 1:
			doctor_id = active_scoped_ids[0]

	try:
		request_obj, allocations = trigger_doctor_day_unavailable(
			doctor_id=doctor_id,
			source_date=source_date,
			actor_username=request.user.username,
			reason=reason,
		)
	except Doctor.DoesNotExist:
		return JsonResponse({"error": "doctor_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) == "no_appointments_for_day":
			return JsonResponse(
				{
					"error": "no_appointments_for_day",
					"debug": {
						"evaluated_doctor_id": doctor_id,
						"source_date": str(source_date),
					},
				},
				status=409,
			)
		raise

	data = {
		"request_id": request_obj.id,
		"doctor_id": request_obj.doctor_id,
		"doctor_name": request_obj.doctor.display_name,
		"source_date": str(request_obj.source_date),
		"target_date": str(request_obj.target_date),
		"status": request_obj.status,
		"total_appointments": request_obj.total_appointments,
		"target_capacity": request_obj.target_capacity,
		"target_existing": request_obj.target_existing,
		"overflow_count": request_obj.overflow_count,
		"allocations": allocations,
	}
	if request_obj.status == "PENDING_RECEPTION":
		return JsonResponse(
			{
				"status": "pending_reception_decision",
				"message": "overflow_detected_reception_decision_required",
				"data": data,
			},
			status=202,
		)

	return JsonResponse(
		{
			"status": "success",
			"message": "appointments_rescheduled",
			"data": data,
		}
	)


@require_GET
@login_required
@role_required("Receptionist", "Admin")
def receptionist_pending_day_reschedules(request):
	items = list_pending_day_reschedule_requests()
	return JsonResponse(
		{
			"count": len(items),
			"items": [
				{
					"request_id": item.id,
					"doctor_id": item.doctor_id,
					"doctor_name": item.doctor.display_name,
					"source_date": str(item.source_date),
					"target_date": str(item.target_date),
					"reason": item.reason,
					"total_appointments": item.total_appointments,
					"target_capacity": item.target_capacity,
					"target_existing": item.target_existing,
					"overflow_count": item.overflow_count,
					"created_at": item.created_at.isoformat(),
				}
				for item in items
			],
		}
	)


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def receptionist_decide_day_reschedule(request, request_id):
	form = ReceptionEmergencyRescheduleDecisionForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	action = (form.cleaned_data["action"] or "").upper()
	try:
		request_obj, allocations = decide_day_reschedule_request(
			request_id=request_id,
			action=action,
			actor_username=request.user.username,
		)
	except DoctorDayRescheduleRequest.DoesNotExist:
		return JsonResponse({"error": "request_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) == "request_not_pending":
			return JsonResponse({"error": "request_not_pending"}, status=409)
		if str(exc) == "invalid_action":
			return JsonResponse({"error": "invalid_action"}, status=400)
		raise

	return JsonResponse(
		{
			"status": "success",
			"message": "reschedule_executed",
			"data": {
				"request_id": request_obj.id,
				"decision": action,
				"doctor_name": request_obj.doctor.display_name,
				"source_date": str(request_obj.source_date),
				"target_date": str(request_obj.target_date),
				"allocations": allocations,
			},
		}
	)


@require_GET
@login_required
@role_required("Admin")
def user_role_management(request):
	users = User.objects.all().order_by("username")
	roles = sorted(ROLE_PERMISSION_MATRIX.keys())
	groups = Group.objects.all().order_by("name")
	user_rows = []
	for user in users:
		user_rows.append(
			{
				"id": user.id,
				"username": user.username,
				"roles": [group.name for group in user.groups.all()],
			}
		)
	role_rows = []
	for group in groups:
		role_rows.append(
			{
				"name": group.name,
				"user_count": group.user_set.count(),
			}
		)

	clinic_settings = ClinicSettings.get_solo()
	logo_url = clinic_settings.logo.url if clinic_settings.logo else ""
	user_roles = set(request.user.groups.values_list("name", flat=True))

	return render(
		request,
		"user_role_management.html",
		{
			"users": user_rows,
			"roles": roles,
			"role_rows": role_rows,
			"current_user_id": request.user.id,
			"clinic_name": clinic_settings.clinic_name,
			"clinic_address": clinic_settings.clinic_address,
			"clinic_phone": clinic_settings.clinic_phone,
			"clinic_mob": clinic_settings.clinic_mob,
			"upi_id": clinic_settings.upi_id,
			"logo_url": logo_url,
			"registration_number": clinic_settings.registration_number,
			"registration_authority": clinic_settings.registration_authority,
			"create_form": UserCreateForm(),
			"assign_form": UserRoleAssignForm(),
			"message": request.GET.get("message", ""),
			"status": request.GET.get("status", ""),
			"is_admin": "Admin" in user_roles,
			"is_doctor": "Doctor" in user_roles,
			"is_receptionist": "Receptionist" in user_roles,
			"is_pharmacist": "Pharmacist" in user_roles,
		},
	)


@require_POST
@login_required
@role_required("Admin")
def user_delete(request):
	user_id_raw = (request.POST.get("user_id") or "").strip()
	if not user_id_raw:
		return _redirect_user_mgmt("error", "User delete failed. Missing user ID.")

	try:
		user_id = int(user_id_raw)
	except ValueError:
		return _redirect_user_mgmt("error", "User delete failed. Invalid user ID.")

	if user_id == request.user.id:
		return _redirect_user_mgmt("error", "You cannot delete the currently logged-in user.")

	try:
		target = User.objects.get(id=user_id)
	except User.DoesNotExist:
		return _redirect_user_mgmt("error", "Selected user was not found.")

	if target.is_superuser and User.objects.filter(is_superuser=True).count() <= 1:
		return _redirect_user_mgmt("error", "Cannot delete the last superuser account.")

	username = target.username
	target.delete()
	return _redirect_user_mgmt("success", f"User {username} deleted successfully.")


@require_POST
@login_required
@role_required("Admin")
def role_delete(request):
	role_name = (request.POST.get("role") or "").strip()
	if not role_name:
		return _redirect_user_mgmt("error", "Role delete failed. Missing role name.")

	if role_name == "Admin":
		return _redirect_user_mgmt("error", "Admin role cannot be deleted.")

	try:
		group = Group.objects.get(name=role_name)
	except Group.DoesNotExist:
		return _redirect_user_mgmt("error", "Selected role was not found.")

	group.delete()
	return _redirect_user_mgmt("success", f"Role {role_name} deleted successfully.")


@require_POST
@login_required
@role_required("Admin")
def clinic_settings_update(request):
	clinic_name = (request.POST.get("clinic_name") or "").strip()
	clinic_address = (request.POST.get("clinic_address") or "").strip()
	clinic_phone = (request.POST.get("clinic_phone") or "").strip()
	clinic_mob = (request.POST.get("clinic_mob") or "").strip()
	upi_id = (request.POST.get("upi_id") or "").strip()
	registration_number = (request.POST.get("registration_number") or "").strip()
	registration_authority = (request.POST.get("registration_authority") or "").strip()
	
	if not clinic_name:
		return _redirect_user_mgmt("error", "Clinic name is required.")
	
	settings = ClinicSettings.get_solo()
	settings.clinic_name = clinic_name
	settings.clinic_address = clinic_address
	settings.clinic_phone = clinic_phone
	settings.clinic_mob = clinic_mob
	settings.upi_id = upi_id
	settings.registration_number = registration_number
	settings.registration_authority = registration_authority
	
	# Handle logo file upload
	if "logo" in request.FILES:
		settings.logo = request.FILES["logo"]
	
	settings.save(update_fields=["clinic_name", "clinic_address", "clinic_phone", "clinic_mob", "upi_id", "registration_number", "registration_authority", "logo", "updated_at"])
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


@require_POST
@login_required
@role_required("Admin")
def admin_doctor_profile_update(request):
	user_id = request.POST.get("doctor_user_id", "").strip()
	if not user_id:
		return _redirect_user_mgmt("error", "Please select a doctor user.")
	try:
		user = User.objects.get(id=user_id)
	except User.DoesNotExist:
		return _redirect_user_mgmt("error", "Selected user was not found.")

	doctor_full_name = (request.POST.get("doctor_full_name") or "").strip() or f"{user.first_name} {user.last_name}".strip() or user.username
	doctor_specialty = (request.POST.get("doctor_specialty") or "General Medicine").strip()
	try:
		doctor_capacity = int(request.POST.get("doctor_daily_patient_capacity") or 50)
		if doctor_capacity < 1:
			raise ValueError
	except ValueError:
		return _redirect_user_mgmt("error", "Daily patient capacity must be a valid number greater than 0.")

	try:
		doctor_opd_new_patient_fee = Decimal(request.POST.get("doctor_opd_new_patient_fee") or "200.00")
		doctor_opd_existing_patient_fee = Decimal(request.POST.get("doctor_opd_existing_patient_fee") or "100.00")
		if doctor_opd_new_patient_fee < 0 or doctor_opd_existing_patient_fee < 0:
			raise ValueError
	except (InvalidOperation, ValueError):
		return _redirect_user_mgmt("error", "OPD fee values must be valid non-negative numbers.")

	Doctor.objects.update_or_create(
		user=user,
		defaults={
			"full_name": doctor_full_name,
			"suffix": (request.POST.get("doctor_suffix") or "Dr").strip() or "Dr",
			"specialty": doctor_specialty,
			"phone": (request.POST.get("doctor_phone") or "").strip(),
			"reg_number": (request.POST.get("doctor_reg_number") or "").strip(),
			"qualification": (request.POST.get("doctor_qualification") or "").strip(),
			"daily_patient_capacity": doctor_capacity,
			"opd_new_patient_fee": doctor_opd_new_patient_fee,
			"opd_existing_patient_fee": doctor_opd_existing_patient_fee,
		},
	)
	return _redirect_user_mgmt("success", f"Doctor profile for {user.username} saved successfully.")


@require_POST
@login_required
@role_required("Admin")
def admin_software_reset(request):
	confirm_text = (request.POST.get("confirm_text") or "").strip().upper()
	if confirm_text != "RESET":
		return _redirect_user_mgmt("error", "Software reset failed. Type RESET to confirm.")

	bootstrap_username = request.user.username
	bootstrap_password_hash = request.user.password
	bootstrap_email = request.user.email
	bootstrap_first_name = request.user.first_name
	bootstrap_last_name = request.user.last_name

	# Full reset: clears all tables including users, roles and sessions.
	call_command("flush", interactive=False, verbosity=0)

	bootstrap_roles()
	admin_group, _ = Group.objects.get_or_create(name="Admin")
	bootstrap_user = User.objects.create(
		username=bootstrap_username,
		email=bootstrap_email,
		first_name=bootstrap_first_name,
		last_name=bootstrap_last_name,
		password=bootstrap_password_hash,
		is_staff=True,
		is_superuser=True,
		is_active=True,
	)
	bootstrap_user.groups.add(admin_group)

	return redirect("/users/manage/?status=success&message=Full+reset+completed.+Admin+account+was+auto-restored.")


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
@role_required("Doctor", "Admin")
def appointment_pause_current(request):
	form = PauseCurrentConsultationForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	doctor_id = form.cleaned_data.get("doctor_id")
	if doctor_id is None:
		doctor_profile = getattr(request.user, "doctor_profile", None)
		if doctor_profile is None:
			return JsonResponse({"error": "doctor_id_required"}, status=400)
		doctor_id = doctor_profile.id

	try:
		queue_item, _, payload = pause_current_consultation(
			doctor_id=doctor_id,
			actor_username=request.user.username,
		)
	except Doctor.DoesNotExist:
		return JsonResponse({"error": "doctor_not_found"}, status=404)
	except ValueError as exc:
		if str(exc) in {"no_consultation_in_progress", "cannot_pause_finalized_consultation", "no_consultation_record"}:
			return JsonResponse({"error": str(exc)}, status=409)
		raise

	return JsonResponse(
		{
			"status": queue_item.status,
			"queue_item_id": queue_item.id,
			"appointment_id": queue_item.appointment_id,
			"paused_at": queue_item.paused_at.isoformat() if queue_item.paused_at else None,
			"event": payload,
		}
	)


@require_POST
@login_required
@role_required("Receptionist", "Admin")
def appointment_add_emergency(request):
	form = AddEmergencyPatientForm(request.POST)
	if not form.is_valid():
		return JsonResponse({"error": "validation_failed", "details": form.errors}, status=400)

	patient_id = form.cleaned_data.get("patient_id")
	if patient_id:
		patient_payload = patient_id
	else:
		patient_payload = {
			"first_name": form.cleaned_data.get("first_name"),
			"last_name": form.cleaned_data.get("last_name"),
			"phone": form.cleaned_data.get("phone"),
		}

	try:
		result = add_emergency_patient(
			patient_id_or_data=patient_payload,
			doctor_id=form.cleaned_data["doctor_id"],
			actor_username=request.user.username,
			visit_type=form.cleaned_data.get("visit_type") or "NEW",
			actor_user_id=request.user.id,
		)
	except Doctor.DoesNotExist:
		return JsonResponse({"error": "doctor_not_found"}, status=404)
	except Patient.DoesNotExist:
		return JsonResponse({"error": "patient_not_found"}, status=404)

	appointment = result["appointment"]
	queue_item = result["queue_item"]
	return JsonResponse(
		{
			"appointment_id": appointment.id,
			"queue_item_id": queue_item.id,
			"queue_status": queue_item.status,
			"queue_position": result["queue_position"],
			"patient_name": result["patient_name"],
			"opd_number": result["opd_number"],
			"is_emergency": appointment.is_emergency,
		},
		status=201,
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
@role_required("Doctor", "Receptionist", "Admin")
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
				"name": _patient_display_name(patient),
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
	patient_id_raw = request.GET.get("patient_id", "").strip()
	opd_number = request.GET.get("opd_number", "").strip()
	name = request.GET.get("name", "").strip()
	phone = request.GET.get("phone", "").strip()
	date_from_raw = request.GET.get("date_from", "").strip()
	date_to_raw = request.GET.get("date_to", "").strip()

	if not patient_id_raw and not opd_number and not name and not phone:
		return JsonResponse({"error": "patient_filter_required"}, status=400)

	queryset = Prescription.objects.select_related("patient", "doctor", "consultation").order_by("-issued_at", "-id")

	if patient_id_raw:
		try:
			patient_id = int(patient_id_raw)
		except ValueError:
			return JsonResponse({"error": "invalid_patient_id"}, status=400)
		queryset = queryset.filter(patient_id=patient_id)

	if opd_number:
		queryset = queryset.filter(patient__opd_number__iexact=opd_number)

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

	if date_from_raw:
		try:
			date_from = datetime.strptime(date_from_raw, "%Y-%m-%d").date()
		except ValueError:
			return JsonResponse({"error": "invalid_date_from"}, status=400)
		queryset = queryset.filter(issued_at__date__gte=date_from)

	if date_to_raw:
		try:
			date_to = datetime.strptime(date_to_raw, "%Y-%m-%d").date()
		except ValueError:
			return JsonResponse({"error": "invalid_date_to"}, status=400)
		queryset = queryset.filter(issued_at__date__lte=date_to)

	if date_from_raw and date_to_raw and date_from > date_to:
		return JsonResponse({"error": "invalid_date_range"}, status=400)

	items = [
		{
			"prescription_id": p.id,
			"consultation_id": p.consultation_id,
			"rx_number": p.rx_number,
			"issued_at": p.issued_at.strftime("%d/%m/%Y %H:%M"),
			"patient_id": p.patient_id,
			"patient_name": _patient_display_name(p.patient),
			"opd_number": p.patient.opd_number,
			"mobile": p.patient.phone,
			"doctor_name": p.doctor.display_name,
			"diagnosis": (p.consultation.diagnosis or "").strip() or (p.consultation.chief_complaint or "").strip(),
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
	marker = "Advise Labs:"
	special_instructions_text = (p.special_instructions or "").strip()
	advise_labs_text = ""
	lower_text = special_instructions_text.lower()
	marker_index = lower_text.find(marker.lower())
	if marker_index >= 0:
		advise_labs_text = special_instructions_text[marker_index + len(marker):].strip()
		special_instructions_text = special_instructions_text[:marker_index].strip()

	clinic_logo_url = p.clinic_logo_url
	if not clinic_logo_url:
		clinic_settings = ClinicSettings.get_solo()
		clinic_logo_url = clinic_settings.logo.url if clinic_settings.logo else ""
	# Backward compatibility for older stored paths before MEDIA_URL was configured.
	if clinic_logo_url.startswith("/clinic_logos/"):
		clinic_logo_url = f"/media{clinic_logo_url}"
	elif clinic_logo_url.startswith("clinic_logos/"):
		clinic_logo_url = f"/media/{clinic_logo_url}"
	# If stored prescription logo path points to a deleted/missing file, fallback to current clinic logo.
	if clinic_logo_url.startswith("/media/"):
		logo_abs_path = os.path.join(str(settings.MEDIA_ROOT), clinic_logo_url[len("/media/"):])
		if not os.path.exists(logo_abs_path):
			clinic_settings = ClinicSettings.get_solo()
			clinic_logo_url = clinic_settings.logo.url if clinic_settings.logo else ""

	clinic_settings = ClinicSettings.get_solo()
	context = {
		"rx_number": p.rx_number,
		"auto_print": request.GET.get("print") == "1",
		"issued_at": p.issued_at,
		"validity_days": p.validity_days,
		"clinic_name": p.clinic_name or _opd_clinic_name(),
		"clinic_address": p.clinic_address or _opd_clinic_address(),
		"clinic_phone": clinic_settings.clinic_phone,
		"clinic_mob": clinic_settings.clinic_mob,
		"clinic_logo_url": clinic_logo_url,
		"doctor_name": doctor.display_name,
		"doctor_specialty": doctor.specialty,
		"doctor_qualification": p.doctor_qualification or doctor.qualification,
		"doctor_reg_number": p.doctor_reg_number or doctor.reg_number,
		"doctor_phone": doctor.phone,
		"patient_name": _patient_display_name(patient),
		"patient_mrn": patient.mrn,
		"patient_age": p.patient_age_at_issue,
		"patient_gender": patient.get_gender_display(),
		"patient_weight_kg": p.patient_weight_kg,
		"patient_phone": patient.phone,
		"diagnosis": consultation.diagnosis,
		"items": p.items,
		"special_instructions": special_instructions_text,
		"advise_labs": advise_labs_text,
		"follow_up_date": consultation.follow_up_date,
		"issued_by": p.issued_by,
	}
	response = render(request, "prescription_print.html", context)
	response["Cache-Control"] = "no-store, no-cache, must-revalidate"
	response["Pragma"] = "no-cache"
	return response


@require_POST
@login_required
@role_required("Doctor", "Admin")
def appointment_complete_after_prescription(request, consultation_id):
	"""
	Mark appointment as completed after prescription is issued.
	This is the 'NEXT patient' button handler.
	"""
	try:
		consultation = Consultation.objects.get(id=consultation_id)
	except Consultation.DoesNotExist:
		return JsonResponse({"error": "consultation_not_found"}, status=404)

	# Get the associated appointment
	appointment = consultation.appointment
	if not appointment:
		return JsonResponse({"error": "appointment_not_found"}, status=404)

	# Ensure billing is finalized so receptionist can collect a single final invoice.
	opd_candidates = [appointment.opd_number]
	patient_opd_number = consultation.patient.opd_number if consultation.patient else ""
	if patient_opd_number and patient_opd_number not in opd_candidates:
		opd_candidates.append(patient_opd_number)

	ledger = (
		BillingLedger.objects.select_related("invoice")
		.filter(opd_number__in=opd_candidates)
		.order_by("-created_at")
		.first()
	)
	if ledger is None:
		return JsonResponse({"error": "billing_ledger_not_found"}, status=409)

	invoice = getattr(ledger, "invoice", None)
	if ledger.status == "OPEN":
		try:
			ledger, invoice = finalize_billing_ledger(
				ledger_id=ledger.id,
				actor_username=request.user.username,
				tax=0,
				discount=0,
			)
		except ValueError as exc:
			return JsonResponse({"error": f"billing_finalize_failed:{str(exc)}"}, status=409)

	# Mark appointment as completed
	try:
		completed_appointment = complete_appointment(appointment, request.user.username)
	except ValueError as exc:
		if str(exc) == "invalid_transition":
			return JsonResponse({"error": "invalid_appointment_status_transition"}, status=409)
		raise

	return JsonResponse({
		"status": completed_appointment.status,
		"appointment_id": completed_appointment.id,
		"opd_number": completed_appointment.opd_number,
		"invoice_id": invoice.id if invoice else None,
		"bill_number": invoice.bill_number if invoice else None,
		"message": "Appointment completed. Ready for next patient."
	})


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
@role_required("Receptionist", "Doctor", "Admin")
def billing_ledger_by_opd_get(request):
	opd_number = request.GET.get("opd_number", "").strip()
	appointment_id_raw = request.GET.get("appointment_id", "").strip()
	appointment_id = None
	if not opd_number:
		return JsonResponse({"error": "opd_number_required"}, status=400)
	if appointment_id_raw:
		try:
			appointment_id = int(appointment_id_raw)
		except ValueError:
			return JsonResponse({"error": "invalid_appointment_id"}, status=400)

	ledger = get_relevant_billing_ledger_for_opd(opd_number, appointment_id=appointment_id)
	if ledger is None:
		ledger = (
			BillingLedger.objects.select_related("patient", "doctor")
			.prefetch_related("line_items")
			.filter(opd_number=opd_number)
			.order_by("-created_at")
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
	except IntegrityError:
		return JsonResponse({"error": "billing_ledger_conflict"}, status=409)

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
@role_required("Receptionist", "Doctor", "Admin")
def billing_ledger_add_line_item(request, ledger_id):
	line_type = request.POST.get("line_type", "").strip()
	amount = request.POST.get("amount", "").strip()
	description = request.POST.get("description", "").strip()
	source_order_id = request.POST.get("source_order_id", "").strip()
	# RCT multi-sitting recovery fields
	total_case_amount = request.POST.get("total_case_amount", "").strip() or None
	recovery_stage_percent_str = request.POST.get("recovery_stage_percent", "").strip() or None
	sitting_number_str = request.POST.get("sitting_number", "").strip() or None
	total_sittings_str = request.POST.get("total_sittings", "").strip() or None
	include_opd_fee_raw = request.POST.get("include_opd_fee", "1").strip().lower()
	include_opd_fee = include_opd_fee_raw not in {"0", "false", "no"}
	
	recovery_stage_percent = int(recovery_stage_percent_str) if recovery_stage_percent_str else None
	sitting_number = int(sitting_number_str) if sitting_number_str else None
	total_sittings = int(total_sittings_str) if total_sittings_str else None
	
	if not line_type or not amount:
		return JsonResponse({"error": "line_type_and_amount_required"}, status=400)

	if request.user.groups.filter(name="Doctor").exists() and line_type not in {"RADIOLOGY", "MISC", "RCT", "OPD_NEW_FEE", "OPD_REPEAT_FEE"}:
		return JsonResponse({"error": "doctor_line_type_not_allowed"}, status=403)

	try:
		item = add_billing_line_item(
			ledger_id=ledger_id,
			line_type=line_type,
			amount=amount,
			actor_username=request.user.username,
			description=description,
			source_order_id=source_order_id,
			total_case_amount=total_case_amount,
			recovery_stage_percent=recovery_stage_percent,
			sitting_number=sitting_number,
			total_sittings=total_sittings,
			include_opd_fee=include_opd_fee,
		)
	except BillingLedger.DoesNotExist:
		return JsonResponse({"error": "ledger_not_found"}, status=404)
	except ValueError as exc:
		return JsonResponse({"error": str(exc)}, status=400)

	return JsonResponse({"status": "success", "message": "line_item_added", "data": _billing_line_item_payload(item)}, status=201)


@login_required
@require_POST
@role_required("Receptionist", "Doctor", "Admin")
def billing_ledger_remove_line_item(request, ledger_id, line_item_id):
	try:
		ledger = BillingLedger.objects.get(id=ledger_id)
	except BillingLedger.DoesNotExist:
		return JsonResponse({"error": "ledger_not_found"}, status=404)

	if ledger.status != "OPEN":
		return JsonResponse({"error": "ledger_not_open"}, status=409)

	try:
		item = BillingLineItem.objects.get(id=line_item_id, ledger_id=ledger.id)
	except BillingLineItem.DoesNotExist:
		return JsonResponse({"error": "line_item_not_found"}, status=404)

	item.delete()
	return JsonResponse({"status": "success", "message": "line_item_removed"})


@login_required
@require_GET
@role_required("Doctor", "Receptionist", "Admin")
def billing_ledger_get_rct_case_amount(request, ledger_id):
	"""
	Fetch the RCT total case amount from the first RCT line item in this ledger.
	Used to auto-fill the Total Case Amount field on subsequent RCT visits.
	"""
	try:
		ledger = BillingLedger.objects.get(id=ledger_id)
	except BillingLedger.DoesNotExist:
		return JsonResponse({"error": "ledger_not_found"}, status=404)
	
	# Find the first RCT line item with a total_case_amount
	rct_item = BillingLineItem.objects.filter(ledger=ledger, total_case_amount__isnull=False).first()
	if rct_item:
		return JsonResponse({
			"status": "success",
			"total_case_amount": float(rct_item.total_case_amount),
			"total_sittings": rct_item.total_sittings,
		})
	return JsonResponse({"status": "success", "total_case_amount": None})


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
	display_total = _invoice_current_total(invoice)
	pending_amount = max(Decimal("0"), (display_total or Decimal("0")) - (invoice.recovered_amount or Decimal("0")))
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
					"name": _patient_display_name(invoice.ledger.patient),
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
					"total": str(display_total),
					"recovered_amount": str(invoice.recovered_amount),
					"pending_amount": str(pending_amount),
				},
				"payment": {
					"status": invoice.payment_status,
					"method": invoice.payment_method or "-",
					"upi_txn_ref": invoice.upi_txn_ref,
					"paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
					"recovered_percentage": invoice.recovered_percentage,
					"recovered_amount": str(invoice.recovered_amount),
					"pending_amount": str(pending_amount),
				},
				"upi": {
					"upi_id": ClinicSettings.get_solo().upi_id or "admin@upi",
					"payee_name": _opd_clinic_name(),
					"intent_uri": (
						f"upi://pay?pa={quote_plus(ClinicSettings.get_solo().upi_id or 'admin@upi')}&pn={quote_plus(_opd_clinic_name())}"
						f"&am={quote_plus(str(display_total))}&cu=INR&tn={quote_plus(invoice.bill_number)}"
					),
					"qr_image_url": (
						"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data="
						+ quote_plus(
							f"upi://pay?pa={ClinicSettings.get_solo().upi_id or 'admin@upi'}&pn={_opd_clinic_name()}&am={display_total}&cu=INR&tn={invoice.bill_number}"
						)
					),
				},
				"print_url": f"/billing/invoice/{invoice.id}/print/",
				"pdf_download_url": f"/api/billing/invoice/{invoice.id}/pdf/",
			},
		}
	)


@login_required
@require_POST
@role_required("Receptionist", "Admin")
def billing_invoice_mark_paid_upi(request, invoice_id):
	upi_txn_ref = (request.POST.get("upi_txn_ref") or "").strip()
	recovery_percent_raw = (request.POST.get("recovery_percent") or "").strip() or "100"

	try:
		invoice = BillingInvoice.objects.get(id=invoice_id)
	except BillingInvoice.DoesNotExist:
		return JsonResponse({"error": "invoice_not_found"}, status=404)

	try:
		recovery_percent = int(recovery_percent_raw)
	except ValueError:
		return JsonResponse({"error": "invalid_recovery_percent"}, status=400)

	allowed_percentages = {25, 50, 75, 100}
	if recovery_percent not in allowed_percentages:
		return JsonResponse({"error": "invalid_recovery_percent"}, status=400)

	if recovery_percent < (invoice.recovered_percentage or 0):
		return JsonResponse({"error": "recovery_percent_cannot_decrease"}, status=409)

	recovered_amount = ((invoice.total or Decimal("0")) * Decimal(recovery_percent) / Decimal("100")).quantize(Decimal("0.01"))
	invoice.recovered_percentage = recovery_percent
	invoice.recovered_amount = recovered_amount
	invoice.payment_status = "DONE" if recovery_percent >= 100 else "PENDING"
	invoice.payment_method = "UPI"
	if upi_txn_ref:
		invoice.upi_txn_ref = upi_txn_ref
	invoice.paid_at = timezone.now()
	invoice.save(update_fields=["payment_status", "payment_method", "upi_txn_ref", "paid_at", "recovered_percentage", "recovered_amount"])

	pending_amount = max(Decimal("0"), (invoice.total or Decimal("0")) - (invoice.recovered_amount or Decimal("0")))

	return JsonResponse(
		{
			"status": "success",
			"message": "payment_marked_done" if invoice.payment_status == "DONE" else "payment_marked_partial",
			"data": {
				"invoice_id": invoice.id,
				"bill_number": invoice.bill_number,
				"payment_status": invoice.payment_status,
				"payment_method": invoice.payment_method,
				"upi_txn_ref": invoice.upi_txn_ref,
				"paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
				"recovered_percentage": invoice.recovered_percentage,
				"recovered_amount": str(invoice.recovered_amount),
				"pending_amount": str(pending_amount),
			},
		}
	)


@login_required
@require_GET
@role_required("Receptionist", "Admin")
def billing_invoice_live_feed(request):
	date_raw = request.GET.get("date", "").strip()
	limit_raw = request.GET.get("limit", "25").strip() or "25"

	if date_raw:
		try:
			filter_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
		except ValueError:
			return JsonResponse({"error": "invalid_date"}, status=400)
	else:
		filter_date = datetime.now().date()

	try:
		limit = max(1, min(int(limit_raw), 100))
	except ValueError:
		return JsonResponse({"error": "invalid_limit"}, status=400)

	invoices = (
		BillingInvoice.objects.select_related("ledger", "ledger__patient", "ledger__doctor")
		.filter(created_at__date=filter_date)
		.order_by("-created_at")[:limit]
	)

	items = []
	for invoice in invoices:
		patient_name = _patient_display_name(invoice.ledger.patient)
		display_total = _invoice_current_total(invoice)
		items.append(
			{
				"invoice_id": invoice.id,
				"bill_number": invoice.bill_number,
				"created_at": invoice.created_at.isoformat(),
				"opd_number": invoice.ledger.opd_number,
				"patient_name": patient_name,
				"doctor_name": invoice.ledger.doctor.display_name,
				"total": str(display_total),
				"payment_status": invoice.payment_status,
				"recovered_percentage": invoice.recovered_percentage,
				"recovered_amount": str(invoice.recovered_amount),
				"payment_method": invoice.payment_method or "-",
				"upi_txn_ref": invoice.upi_txn_ref,
				"print_url": f"/billing/invoice/{invoice.id}/print/",
				"pdf_download_url": f"/api/billing/invoice/{invoice.id}/pdf/",
			}
		)

	return JsonResponse(
		{
			"status": "success",
			"message": "live_invoice_feed_fetched",
			"data": {
				"date": str(filter_date),
				"count": len(items),
				"invoices": items,
			},
		}
	)


@login_required
@require_GET
@role_required("Receptionist", "Admin")
def billing_invoice_history_by_patient(request):
	patient_id_raw = request.GET.get("patient_id", "").strip()
	opd_number = request.GET.get("opd_number", "").strip()
	doctor_name = request.GET.get("doctor_name", "").strip()
	date_from = request.GET.get("date_from", "").strip()
	date_to = request.GET.get("date_to", "").strip()
	min_total_raw = request.GET.get("min_total", "").strip()
	max_total_raw = request.GET.get("max_total", "").strip()

	patient = None
	if patient_id_raw:
		try:
			patient = Patient.objects.get(id=int(patient_id_raw))
		except (ValueError, Patient.DoesNotExist):
			return JsonResponse({"error": "patient_not_found"}, status=404)
	elif opd_number:
		patient = Patient.objects.filter(opd_number=opd_number).first()
		if patient is None:
			return JsonResponse({"error": "patient_not_found"}, status=404)
	else:
		return JsonResponse({"error": "patient_id_or_opd_number_required"}, status=400)

	invoices = (
		BillingInvoice.objects.select_related("ledger", "ledger__patient", "ledger__doctor")
		.filter(ledger__patient_id=patient.id)
	)
	if opd_number:
		invoices = invoices.filter(ledger__opd_number=opd_number)

	if doctor_name:
		invoices = invoices.filter(ledger__doctor__full_name__icontains=doctor_name)

	if date_from:
		try:
			datetime.strptime(date_from, "%Y-%m-%d")
		except ValueError:
			return JsonResponse({"error": "invalid_date_from"}, status=400)
		invoices = invoices.filter(created_at__date__gte=date_from)

	if date_to:
		try:
			datetime.strptime(date_to, "%Y-%m-%d")
		except ValueError:
			return JsonResponse({"error": "invalid_date_to"}, status=400)
		invoices = invoices.filter(created_at__date__lte=date_to)

	if min_total_raw:
		try:
			min_total = Decimal(min_total_raw)
		except InvalidOperation:
			return JsonResponse({"error": "invalid_min_total"}, status=400)
		invoices = invoices.filter(total__gte=min_total)

	if max_total_raw:
		try:
			max_total = Decimal(max_total_raw)
		except InvalidOperation:
			return JsonResponse({"error": "invalid_max_total"}, status=400)
		invoices = invoices.filter(total__lte=max_total)

	invoices = invoices.order_by("-created_at")

	items = []
	for invoice in invoices:
		display_total = _invoice_current_total(invoice)
		items.append(
			{
				"invoice_id": invoice.id,
				"bill_number": invoice.bill_number,
				"created_at": invoice.created_at.isoformat(),
				"opd_number": invoice.ledger.opd_number,
				"visit_date": str(invoice.ledger.visit_date),
				"doctor_name": invoice.ledger.doctor.display_name,
				"subtotal": str(invoice.subtotal),
				"discount": str(invoice.discount),
				"tax": str(invoice.tax),
				"total": str(display_total),
				"recovered_percentage": invoice.recovered_percentage,
				"recovered_amount": str(invoice.recovered_amount),
				"pending_amount": str(max(Decimal("0"), (display_total or Decimal("0")) - (invoice.recovered_amount or Decimal("0")))),
				"print_url": f"/billing/invoice/{invoice.id}/print/",
				"pdf_download_url": f"/api/billing/invoice/{invoice.id}/pdf/",
			}
		)

	return JsonResponse(
		{
			"status": "success",
			"message": "invoice_history_fetched",
			"data": {
				"patient": {
					"patient_id": patient.id,
					"name": _patient_display_name(patient),
					"phone": patient.phone,
					"opd_number": patient.opd_number,
				},
				"filters": {
					"doctor_name": doctor_name,
					"date_from": date_from,
					"date_to": date_to,
					"min_total": min_total_raw,
					"max_total": max_total_raw,
				},
				"invoices": items,
				"count": len(items),
			},
		}
	)


@login_required
@require_http_methods(["DELETE"])
@role_required("Receptionist", "Admin")
def billing_invoice_void(request, invoice_id):
	"""Void (delete) a finalized invoice and reopen its ledger for corrections."""
	try:
		invoice = BillingInvoice.objects.select_related("ledger").get(id=invoice_id)
	except BillingInvoice.DoesNotExist:
		return JsonResponse({"error": "invoice_not_found"}, status=404)

	if invoice.payment_status == "DONE":
		return JsonResponse({"error": "paid_invoice_cannot_be_voided"}, status=400)

	ledger = invoice.ledger
	invoice.delete()
	ledger.status = "OPEN"
	ledger.finalized_by = ""
	ledger.finalized_at = None
	ledger.save(update_fields=["status", "finalized_by", "finalized_at"])

	return JsonResponse({"status": "success", "message": "invoice_voided"})


@login_required
@require_POST
@role_required("Receptionist", "Admin")
def billing_invoice_update(request, invoice_id):
	"""Update invoice discount, tax, and/or individual line item amounts/descriptions."""
	try:
		invoice = BillingInvoice.objects.select_related("ledger").get(id=invoice_id)
	except BillingInvoice.DoesNotExist:
		return JsonResponse({"error": "invoice_not_found"}, status=404)

	if invoice.payment_status == "DONE":
		return JsonResponse({"error": "paid_invoice_cannot_be_updated"}, status=400)

	discount_raw = (request.POST.get("discount") or "").strip()
	tax_raw = (request.POST.get("tax") or "").strip()

	try:
		new_discount = Decimal(discount_raw) if discount_raw else invoice.discount
		new_tax = Decimal(tax_raw) if tax_raw else invoice.tax
	except InvalidOperation:
		return JsonResponse({"error": "invalid_discount_or_tax"}, status=400)

	if new_discount < Decimal("0") or new_tax < Decimal("0"):
		return JsonResponse({"error": "discount_and_tax_must_be_non_negative"}, status=400)

	# Update line items if provided (format: line_item_{id}_amount, line_item_{id}_description)
	line_items = list(BillingLineItem.objects.filter(ledger_id=invoice.ledger_id))
	for item in line_items:
		amount_key = f"line_item_{item.id}_amount"
		desc_key = f"line_item_{item.id}_description"
		changed = False
		if amount_key in request.POST:
			try:
				item.amount = Decimal(request.POST[amount_key])
				changed = True
			except InvalidOperation:
				return JsonResponse({"error": f"invalid_amount_for_line_item_{item.id}"}, status=400)
		if desc_key in request.POST:
			item.description = (request.POST[desc_key] or "").strip()[:255]
			changed = True
		if changed:
			item.save(update_fields=["amount", "description"])

	# Recalculate totals
	line_items_fresh = BillingLineItem.objects.filter(ledger_id=invoice.ledger_id)
	new_subtotal = sum(item.amount for item in line_items_fresh)
	new_total = max(Decimal("0"), new_subtotal - new_discount + new_tax)

	invoice.subtotal = new_subtotal
	invoice.discount = new_discount
	invoice.tax = new_tax
	invoice.total = new_total
	invoice.save(update_fields=["subtotal", "discount", "tax", "total"])

	return JsonResponse({
		"status": "success",
		"message": "invoice_updated",
		"data": {
			"invoice_id": invoice.id,
			"bill_number": invoice.bill_number,
			"subtotal": str(invoice.subtotal),
			"discount": str(invoice.discount),
			"tax": str(invoice.tax),
			"total": str(invoice.total),
		},
	})


@login_required
@require_GET
@role_required("Receptionist", "Admin")
@xframe_options_sameorigin
def billing_invoice_print(request, invoice_id):
	try:
		invoice = BillingInvoice.objects.select_related("ledger", "ledger__patient", "ledger__doctor").get(id=invoice_id)
	except BillingInvoice.DoesNotExist:
		return JsonResponse({"error": "invoice_not_found"}, status=404)

	prev_inv_id = request.GET.get("previous_invoice_id", "")
	context = _invoice_print_context(
		invoice,
		auto_print=request.GET.get("print") == "1",
		previous_bill_no=request.GET.get("previous_bill_no", ""),
		previous_visit_date=request.GET.get("previous_visit_date", ""),
		previous_payment_status=request.GET.get("previous_payment_status", ""),
		previous_invoice_id=int(prev_inv_id) if prev_inv_id.isdigit() else None,
	)
	return render(request, "billing_invoice_print.html", context)


@login_required
@require_GET
@role_required("Receptionist", "Admin")
def billing_invoice_pdf_download(request, invoice_id):
	try:
		invoice = BillingInvoice.objects.select_related("ledger", "ledger__patient", "ledger__doctor").get(id=invoice_id)
	except BillingInvoice.DoesNotExist:
		return JsonResponse({"error": "invoice_not_found"}, status=404)

	prev_inv_id = request.GET.get("previous_invoice_id", "")
	context = _invoice_print_context(
		invoice,
		auto_print=True,
		previous_bill_no=request.GET.get("previous_bill_no", ""),
		previous_visit_date=request.GET.get("previous_visit_date", ""),
		previous_payment_status=request.GET.get("previous_payment_status", ""),
		previous_invoice_id=int(prev_inv_id) if prev_inv_id.isdigit() else None,
	)
	return render(request, "billing_invoice_print.html", context)


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


@login_required
@require_GET
@role_required("Doctor", "Receptionist", "Admin")
def medicine_search(request):
	"""Return medicine names matching ?q= for autocomplete (max 20)."""
	q = (request.GET.get("q") or "").strip()
	if not q or len(q) < 2:
		return JsonResponse({"results": []})
	matches = (
		Medicine.objects.filter(name__icontains=q, is_active=True)
		.values("name", "category", "default_strength")[:20]
	)
	return JsonResponse({"results": list(matches)})


@login_required
@require_GET
@role_required("Admin")
def medicine_management_page(request):
	"""Admin page to manage medicines."""
	medicines = Medicine.objects.all().order_by("name")
	categories = [c[0] for c in Medicine.CATEGORY_CHOICES]
	return render(
		request,
		"medicine_management.html",
		{"medicines": medicines, "categories": categories},
	)


@login_required
@require_POST
@role_required("Admin")
def medicine_create(request):
	"""Create or update a medicine."""
	name = (request.POST.get("name") or "").strip()
	category = (request.POST.get("category") or "other").strip()
	default_strength = (request.POST.get("default_strength") or "").strip()
	is_active_raw = request.POST.get("is_active", "on")
	is_active = is_active_raw.lower() in ("on", "true", "1", "yes")

	if not name:
		return JsonResponse({"error": "medicine_name_required"}, status=400)

	if category not in [c[0] for c in Medicine.CATEGORY_CHOICES]:
		return JsonResponse({"error": "invalid_category"}, status=400)

	try:
		medicine, created = Medicine.objects.get_or_create(
			name=name,
			defaults={
				"category": category,
				"default_strength": default_strength,
				"is_active": is_active,
			},
		)
		if not created:
			medicine.category = category
			medicine.default_strength = default_strength
			medicine.is_active = is_active
			medicine.save(update_fields=["category", "default_strength", "is_active"])

		return JsonResponse(
			{
				"status": "success",
				"message": "medicine_created" if created else "medicine_updated",
				"data": {
					"id": medicine.id,
					"name": medicine.name,
					"category": medicine.category,
					"default_strength": medicine.default_strength,
					"is_active": medicine.is_active,
				},
			}
		)
	except Exception as e:
		return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
@role_required("Admin")
def medicine_toggle_active(request, medicine_id):
	"""Toggle medicine active status."""
	try:
		medicine = Medicine.objects.get(id=medicine_id)
	except Medicine.DoesNotExist:
		return JsonResponse({"error": "medicine_not_found"}, status=404)

	medicine.is_active = not medicine.is_active
	medicine.save(update_fields=["is_active"])

	return JsonResponse(
		{
			"status": "success",
			"data": {"id": medicine.id, "is_active": medicine.is_active},
		}
	)


@login_required
@require_GET
@role_required("Admin")
def medicine_list_api(request):
	"""List all medicines for admin API."""
	medicines = Medicine.objects.all().order_by("name")
	return JsonResponse(
		{
			"status": "success",
			"data": [
				{
					"id": m.id,
					"name": m.name,
					"category": m.category,
					"default_strength": m.default_strength,
					"is_active": m.is_active,
				}
				for m in medicines
			],
		}
	)
