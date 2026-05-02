from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal

from .models import (
    Appointment,
    AlertEvent,
    AppointmentEvent,
    BillingHandoff,
    BillingInvoice,
    BillingLedger,
    BillingLineItem,
    BillingAuditEvent,
    BillingRetryLog,
    Consultation,
    ClinicSettings,
    ConsultationAmendment,
    Doctor,
    MedicalOrder,
    Prescription,
    QueueEvent,
    QueueItem,
    ReportExport,
    ReportExportAudit,
    IncidentRecord,
    Vitals,
    DoctorScheduleTemplate,
    DoctorSlot,
    Patient,
    SearchAuditLog,
)


ROLE_PERMISSION_MATRIX = {
    "Receptionist": ["view_patient", "add_patient", "change_patient"],
    "Doctor": ["view_patient"],
    "Pharmacist": ["view_patient"],
    "Admin": ["view_patient", "add_patient", "change_patient", "delete_patient"],
}

APPOINTMENT_TRANSITIONS = {
    "BOOKED": {"RESCHEDULED", "COMPLETED", "CANCELLED"},
    "RESCHEDULED": {"RESCHEDULED", "COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}

QUEUE_TRANSITIONS = {
    "WAITING": {"SKIPPED", "NO_SHOW", "COMPLETED", "CALLED"},
    "CALLED": {"SKIPPED", "NO_SHOW", "COMPLETED"},
    "SKIPPED": {"CALLED", "NO_SHOW", "COMPLETED"},
    "COMPLETED": set(),
    "NO_SHOW": set(),
}


def health_payload():
    return {"status": "ok", "service": "opd-management"}


def bootstrap_roles():
    created = []
    for role_name, codenames in ROLE_PERMISSION_MATRIX.items():
        group, _ = Group.objects.get_or_create(name=role_name)
        perms = Permission.objects.filter(codename__in=codenames)
        group.permissions.set(perms)
        created.append(role_name)
    return created


def find_duplicate_candidates(cleaned_data):
    phone = cleaned_data.get("phone", "")
    national_id = cleaned_data.get("national_id", "")
    first_name = cleaned_data.get("first_name", "")
    last_name = cleaned_data.get("last_name", "")
    dob = cleaned_data.get("dob")

    query = Q(phone=phone)
    if national_id:
        query |= Q(national_id=national_id)
    if first_name and last_name and dob:
        query |= Q(first_name__iexact=first_name, last_name__iexact=last_name, dob=dob)

    return Patient.objects.filter(query).distinct()


def search_patients(mrn="", phone="", name="", dob="", age=None, opd_number=""):
    queryset = Patient.objects.all()

    def _safe_year_replace(date_obj, year):
        try:
            return date_obj.replace(year=year)
        except ValueError:
            return date_obj.replace(month=2, day=28, year=year)

    if mrn:
        queryset = queryset.filter(mrn__iexact=mrn)
    if opd_number:
        queryset = queryset.filter(opd_number__iexact=opd_number)
    if phone:
        queryset = queryset.filter(phone=phone)
    if name:
        name_parts = [part for part in name.strip().split(" ") if part]
        if len(name_parts) >= 2:
            queryset = queryset.filter(first_name__iexact=name_parts[0], last_name__iexact=" ".join(name_parts[1:]))
        else:
            queryset = queryset.filter(Q(first_name__iexact=name) | Q(last_name__iexact=name))
    if dob:
        queryset = queryset.filter(dob=dob)
    if age is not None:
        today = timezone.localdate()
        min_dob = _safe_year_replace(today, today.year - age - 1) + timedelta(days=1)
        max_dob = _safe_year_replace(today, today.year - age)
        queryset = queryset.filter(dob__gte=min_dob, dob__lte=max_dob)

    return queryset.distinct()


def log_search(actor_username, query_type, query_value, result_count):
    return SearchAuditLog.objects.create(
        actor_username=actor_username,
        query_type=query_type,
        query_value=query_value,
        result_count=result_count,
    )


def generate_slots_for_day(slot_date, start_time, end_time, break_start, break_end, slot_minutes):
    slots = []
    start_dt = datetime.combine(slot_date, start_time)
    end_dt = datetime.combine(slot_date, end_time)
    break_start_dt = datetime.combine(slot_date, break_start) if break_start else None
    break_end_dt = datetime.combine(slot_date, break_end) if break_end else None

    cursor = start_dt
    delta = timedelta(minutes=slot_minutes)
    while cursor + delta <= end_dt:
        candidate_start = cursor
        candidate_end = cursor + delta
        overlaps_break = (
            break_start_dt
            and break_end_dt
            and candidate_start < break_end_dt
            and candidate_end > break_start_dt
        )
        if not overlaps_break:
            slots.append((candidate_start.time(), candidate_end.time()))
        cursor = cursor + delta
    return slots


@transaction.atomic
def upsert_doctor_schedule(data, actor_username):
    doctor, _ = Doctor.objects.get_or_create(
        full_name=data["doctor_name"],
        defaults={
            "specialty": data["specialty"],
            "daily_patient_capacity": data.get("daily_patient_capacity") or 50,
        },
    )
    if doctor.specialty != data["specialty"]:
        doctor.specialty = data["specialty"]
        doctor.save(update_fields=["specialty"])

    if data.get("daily_patient_capacity") and doctor.daily_patient_capacity != data["daily_patient_capacity"]:
        doctor.daily_patient_capacity = data["daily_patient_capacity"]
        doctor.save(update_fields=["daily_patient_capacity"])

    schedule, created = DoctorScheduleTemplate.objects.get_or_create(
        doctor=doctor,
        day_of_week=data["day_of_week"],
        defaults={
            "daily_patient_capacity": data.get("daily_patient_capacity") or doctor.daily_patient_capacity,
            "start_time": data["start_time"],
            "end_time": data["end_time"],
            "break_start": data.get("break_start"),
            "break_end": data.get("break_end"),
            "slot_minutes": data["slot_minutes"],
            "version": 1,
            "change_reason": data["reason"],
            "updated_by": actor_username,
        },
    )

    if not created:
        schedule.version += 1
        schedule.daily_patient_capacity = data.get("daily_patient_capacity") or doctor.daily_patient_capacity
        schedule.start_time = data["start_time"]
        schedule.end_time = data["end_time"]
        schedule.break_start = data.get("break_start")
        schedule.break_end = data.get("break_end")
        schedule.slot_minutes = data["slot_minutes"]
        schedule.change_reason = data["reason"]
        schedule.updated_by = actor_username
        schedule.save()

    generated_count = 0
    day_cursor = data["range_start"]
    while day_cursor <= data["range_end"]:
        if day_cursor.weekday() == schedule.day_of_week:
            DoctorSlot.objects.filter(doctor=doctor, slot_date=day_cursor).delete()
            day_slots = generate_slots_for_day(
                day_cursor,
                schedule.start_time,
                schedule.end_time,
                schedule.break_start,
                schedule.break_end,
                schedule.slot_minutes,
            )
            for start, end in day_slots:
                DoctorSlot.objects.create(
                    doctor=doctor,
                    slot_date=day_cursor,
                    start_time=start,
                    end_time=end,
                )
            generated_count += len(day_slots)
        day_cursor = day_cursor + timedelta(days=1)

    return {
        "doctor_id": doctor.id,
        "schedule_version": schedule.version,
        "generated_slots": generated_count,
    }


def is_transition_allowed(current_status, target_status):
    return target_status in APPOINTMENT_TRANSITIONS.get(current_status, set())


def _validate_slot_exists(doctor_id, slot_date, start_time, end_time):
    return DoctorSlot.objects.filter(
        doctor_id=doctor_id,
        slot_date=slot_date,
        start_time=start_time,
        end_time=end_time,
        status="AVAILABLE",
    ).exists()


def _get_available_slot(doctor_id, slot_date, start_time):
    return DoctorSlot.objects.filter(
        doctor_id=doctor_id,
        slot_date=slot_date,
        start_time=start_time,
        status="AVAILABLE",
    ).first()


def _get_available_slot_by_token(doctor_id, slot_date, token):
    if token < 1:
        return None
    slots = DoctorSlot.objects.filter(
        doctor_id=doctor_id,
        slot_date=slot_date,
        status="AVAILABLE",
    ).order_by("start_time")
    return slots[token - 1] if slots.count() >= token else None


def get_doctor_capacity_for_date(doctor, slot_date):
    schedule = DoctorScheduleTemplate.objects.filter(
        doctor_id=doctor.id,
        day_of_week=slot_date.weekday(),
    ).first()
    if schedule and schedule.daily_patient_capacity:
        return schedule.daily_patient_capacity
    return doctor.daily_patient_capacity


def _is_overbooked(doctor_id, slot_date, skip_appointment_id=None):
    doctor = Doctor.objects.get(id=doctor_id)
    capacity = get_doctor_capacity_for_date(doctor, slot_date)
    active = Appointment.objects.filter(doctor_id=doctor_id, slot_date=slot_date).exclude(status="CANCELLED")
    if skip_appointment_id:
        active = active.exclude(id=skip_appointment_id)
    return active.count() >= capacity


@transaction.atomic
def book_appointment(data, actor_username):
    patient = Patient.objects.get(id=data["patient_id"])
    doctor = Doctor.objects.get(id=data["doctor_id"])
    token = data.get("token")
    start_time = data.get("start_time")

    if token:
        slot = _get_available_slot_by_token(doctor.id, data["slot_date"], token)
    else:
        slot = _get_available_slot(doctor.id, data["slot_date"], start_time)

    if not slot:
        raise ValueError("invalid_token" if token else "invalid_slot")
    if _is_overbooked(doctor.id, data["slot_date"]):
        raise ValueError("doctor_daily_capacity_reached")

    appointment = Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        slot_date=data["slot_date"],
        start_time=slot.start_time,
        end_time=slot.end_time,
        visit_type=data["visit_type"],
        channel=data["channel"],
        status="BOOKED",
    )
    AppointmentEvent.objects.create(
        appointment=appointment,
        action="BOOK",
        previous_status="",
        new_status="BOOKED",
        reason="initial_booking",
        actor_username=actor_username,
    )
    return appointment


@transaction.atomic
def reschedule_appointment(appointment, data, actor_username):
    target_status = "RESCHEDULED"
    if not is_transition_allowed(appointment.status, target_status):
        raise ValueError("invalid_transition")

    token = data.get("token")
    if token:
        slot = _get_available_slot_by_token(appointment.doctor_id, data["slot_date"], token)
        if not slot:
            raise ValueError("invalid_token")
        start_time = slot.start_time
        end_time = slot.end_time
    else:
        if not _validate_slot_exists(appointment.doctor_id, data["slot_date"], data["start_time"], data["end_time"]):
            raise ValueError("invalid_slot")
        start_time = data["start_time"]
        end_time = data["end_time"]

    if _is_overbooked(appointment.doctor_id, data["slot_date"], skip_appointment_id=appointment.id):
        raise ValueError("doctor_daily_capacity_reached")

    previous = appointment.status
    appointment.slot_date = data["slot_date"]
    appointment.start_time = start_time
    appointment.end_time = end_time
    appointment.status = target_status
    appointment.save()

    AppointmentEvent.objects.create(
        appointment=appointment,
        action="RESCHEDULE",
        previous_status=previous,
        new_status=target_status,
        reason=data["reason"],
        actor_username=actor_username,
    )
    return appointment


@transaction.atomic
def cancel_appointment(appointment, reason, actor_username):
    target_status = "CANCELLED"
    if not is_transition_allowed(appointment.status, target_status):
        raise ValueError("invalid_transition")

    previous = appointment.status
    appointment.status = target_status
    appointment.save(update_fields=["status", "updated_at"])

    AppointmentEvent.objects.create(
        appointment=appointment,
        action="CANCEL",
        previous_status=previous,
        new_status=target_status,
        reason=reason,
        actor_username=actor_username,
    )
    return appointment


@transaction.atomic
def complete_appointment(appointment, actor_username):
    target_status = "COMPLETED"
    if not is_transition_allowed(appointment.status, target_status):
        raise ValueError("invalid_transition")

    previous = appointment.status
    appointment.status = target_status
    appointment.save(update_fields=["status", "updated_at"])

    AppointmentEvent.objects.create(
        appointment=appointment,
        action="COMPLETE",
        previous_status=previous,
        new_status=target_status,
        reason="doctor_completed_visit",
        actor_username=actor_username,
    )

    queue_item = QueueItem.objects.select_for_update().filter(appointment=appointment).first()
    if queue_item and queue_item.status != "COMPLETED":
        previous_queue_status = queue_item.status
        queue_item.status = "COMPLETED"
        queue_item.save(update_fields=["status", "updated_at"])
        _create_queue_event(queue_item, "COMPLETE", previous_queue_status, "COMPLETED", actor_username)

    return appointment


@transaction.atomic
def queue_mark_called_for_appointment(appointment_id, actor_username):
    appointment = Appointment.objects.select_related("doctor").get(id=appointment_id)
    sync_queue_for_day(appointment.doctor_id, appointment.slot_date)

    queue_item = QueueItem.objects.select_for_update().filter(appointment_id=appointment_id).first()
    if queue_item is None:
        raise QueueItem.DoesNotExist()

    if queue_item.status == "CALLED":
        return queue_item
    if queue_item.status in {"COMPLETED", "NO_SHOW"}:
        raise ValueError("invalid_transition")

    previous = queue_item.status
    queue_item.status = "CALLED"
    queue_item.called_at = timezone.now()
    queue_item.save(update_fields=["status", "called_at", "updated_at"])
    _create_queue_event(queue_item, "RECALL", previous, "CALLED", actor_username)
    return queue_item


def patient_opd_history(patient_id, limit=20):
    qs = (
        Appointment.objects.filter(patient_id=patient_id)
        .exclude(opd_number__isnull=True)
        .exclude(opd_number="")
        .order_by("-created_at")[:limit]
    )
    return list(qs)


def doctor_appointments_for_day(doctor_id, for_date):
    return list(
        Appointment.objects.select_related("patient")
        .filter(doctor_id=doctor_id, slot_date=for_date)
        .exclude(status="CANCELLED")
        .order_by("start_time")
    )


def tomorrow_reminder_report(doctor_id=None):
    target_date = timezone.localdate() + timedelta(days=1)
    qs = Appointment.objects.select_related("patient", "doctor").filter(slot_date=target_date).exclude(status="CANCELLED")
    if doctor_id:
        qs = qs.filter(doctor_id=doctor_id)
    qs = qs.order_by("doctor__full_name", "start_time")
    return target_date, list(qs)


def _queue_transition_allowed(current_status, target_status):
    return target_status in QUEUE_TRANSITIONS.get(current_status, set())


def _next_token_number(doctor_id, slot_date):
    latest = QueueItem.objects.filter(doctor_id=doctor_id, slot_date=slot_date).order_by("-token_number").first()
    return (latest.token_number + 1) if latest else 1


def sync_queue_for_day(doctor_id, slot_date):
    active_appointments = Appointment.objects.filter(
        doctor_id=doctor_id,
        slot_date=slot_date,
        status__in=["BOOKED", "RESCHEDULED"],
    ).order_by("created_at")

    created_count = 0
    for appointment in active_appointments:
        if hasattr(appointment, "queue_item"):
            continue
        QueueItem.objects.create(
            appointment=appointment,
            doctor_id=doctor_id,
            slot_date=slot_date,
            token_number=_next_token_number(doctor_id, slot_date),
            status="WAITING",
        )
        created_count += 1
    return created_count


def _queue_event_payload(queue_item, action, previous_status, new_status):
    return {
        "queue_item_id": queue_item.id,
        "appointment_id": queue_item.appointment_id,
        "doctor_id": queue_item.doctor_id,
        "slot_date": str(queue_item.slot_date),
        "token_number": queue_item.token_number,
        "action": action,
        "previous_status": previous_status,
        "new_status": new_status,
    }


def _create_queue_event(queue_item, action, previous_status, new_status, actor_username):
    payload = _queue_event_payload(queue_item, action, previous_status, new_status)
    event = QueueEvent.objects.create(
        queue_item=queue_item,
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        actor_username=actor_username,
        payload=payload,
    )
    return event, payload


def list_queue_board(doctor_id, slot_date):
    sync_queue_for_day(doctor_id, slot_date)
    items = QueueItem.objects.filter(doctor_id=doctor_id, slot_date=slot_date).order_by("token_number")
    board = []
    waiting_position = 0
    for item in items:
        if item.status in {"WAITING", "CALLED", "SKIPPED"}:
            waiting_position += 1
            estimated_wait_minutes = max(waiting_position - 1, 0) * 10
        else:
            estimated_wait_minutes = 0
        board.append(
            {
                "queue_item_id": item.id,
                "appointment_id": item.appointment_id,
                "token_number": item.token_number,
                "status": item.status,
                "estimated_wait_minutes": estimated_wait_minutes,
            }
        )
    return board


@transaction.atomic
def call_next(doctor_id, slot_date, actor_username):
    sync_queue_for_day(doctor_id, slot_date)
    queue_item = (
        QueueItem.objects.select_for_update()
        .filter(doctor_id=doctor_id, slot_date=slot_date, status="WAITING")
        .order_by("token_number")
        .first()
    )
    if not queue_item:
        raise ValueError("queue_empty")

    previous = queue_item.status
    queue_item.status = "CALLED"
    queue_item.called_at = timezone.now()
    queue_item.save(update_fields=["status", "called_at", "updated_at"])
    event, payload = _create_queue_event(queue_item, "CALL_NEXT", previous, "CALLED", actor_username)
    return queue_item, event, payload


@transaction.atomic
def queue_action(queue_item_id, action, actor_username):
    queue_item = QueueItem.objects.select_for_update().get(id=queue_item_id)
    action_map = {
        "SKIP": "SKIPPED",
        "RECALL": "CALLED",
        "NO_SHOW": "NO_SHOW",
    }
    if action not in action_map:
        raise ValueError("invalid_action")

    target_status = action_map[action]
    if not _queue_transition_allowed(queue_item.status, target_status):
        raise ValueError("invalid_transition")

    previous = queue_item.status
    queue_item.status = target_status
    if target_status == "CALLED":
        queue_item.called_at = timezone.now()
        queue_item.save(update_fields=["status", "called_at", "updated_at"])
    else:
        queue_item.save(update_fields=["status", "updated_at"])

    event, payload = _create_queue_event(queue_item, action, previous, target_status, actor_username)
    return queue_item, event, payload


# ---------------------------------------------------------------------------
# Story 3.1 – Consultation drafting and finalization
# ---------------------------------------------------------------------------

CONSULTATION_EDITABLE_FIELDS = {"chief_complaint", "findings", "diagnosis", "notes", "follow_up_date"}


@transaction.atomic
def create_or_update_consultation_draft(appointment_id, data, actor_username):
    appointment = Appointment.objects.get(id=appointment_id)
    consultation, _ = Consultation.objects.get_or_create(
        appointment=appointment,
        defaults={
            "doctor_id": appointment.doctor_id,
            "patient_id": appointment.patient_id,
            "created_by": actor_username,
        },
    )
    if consultation.status == "FINALIZED":
        raise ValueError("already_finalized")

    for field in CONSULTATION_EDITABLE_FIELDS:
        if field in data:
            setattr(consultation, field, data[field])
    consultation.save()
    return consultation


@transaction.atomic
def finalize_consultation(consultation_id, actor_username):
    consultation = Consultation.objects.select_for_update().get(id=consultation_id)
    if consultation.status == "FINALIZED":
        raise ValueError("already_finalized")

    consultation.status = "FINALIZED"
    consultation.finalized_by = actor_username
    consultation.finalized_at = timezone.now()
    consultation.save(update_fields=["status", "finalized_by", "finalized_at", "updated_at"])
    return consultation


# ---------------------------------------------------------------------------
# Story 3.2 – Vitals + controlled amendments
# ---------------------------------------------------------------------------

VITALS_FIELDS = {"temperature_c", "pulse_bpm", "bp_systolic", "bp_diastolic", "spo2_pct", "weight_kg", "height_cm"}
AMEND_ALLOWED_FIELDS = CONSULTATION_EDITABLE_FIELDS


@transaction.atomic
def record_vitals(consultation_id, data, actor_username):
    consultation = Consultation.objects.get(id=consultation_id)
    vitals, created = Vitals.objects.get_or_create(
        consultation=consultation,
        defaults={"patient_id": consultation.patient_id, "recorded_by": actor_username},
    )
    for field in VITALS_FIELDS:
        if field in data and data[field] is not None:
            setattr(vitals, field, data[field])
    if not created:
        vitals.recorded_by = actor_username
    vitals.save()
    return vitals


@transaction.atomic
def amend_consultation(consultation_id, field_name, new_value, reason, actor_username):
    if field_name not in AMEND_ALLOWED_FIELDS:
        raise ValueError("invalid_field")

    consultation = Consultation.objects.select_for_update().get(id=consultation_id)
    if consultation.status != "FINALIZED":
        raise ValueError("not_finalized")

    previous_value = str(getattr(consultation, field_name) or "")
    setattr(consultation, field_name, new_value)
    consultation.save(update_fields=[field_name, "updated_at"])

    amendment = ConsultationAmendment.objects.create(
        consultation=consultation,
        field_name=field_name,
        previous_value=previous_value,
        new_value=new_value,
        reason=reason,
        actor_username=actor_username,
    )
    return amendment


# ---------------------------------------------------------------------------
# Story 3.3 – E-prescription (Indian format) and basic medical orders
# ---------------------------------------------------------------------------

# Required fields per Rx item (Indian prescription standard)
REQUIRED_PRESCRIPTION_ITEM_KEYS = {"drug", "dosage_form", "strength", "dose", "frequency", "duration", "timing", "route"}

VALID_FREQUENCIES = {"OD", "BD", "TDS", "QID", "SOS", "STAT", "HS", "AC", "PC"}
VALID_TIMINGS = {"before_food", "after_food", "with_food", "empty_stomach", "bedtime", "as_directed"}
VALID_ROUTES = {"oral", "topical", "iv", "im", "sc", "sublingual", "inhalation", "nasal", "rectal", "ophthalmic", "otic"}


def _validate_prescription_items(items):
    if not items:
        raise ValueError("prescription_items_empty")
    for idx, item in enumerate(items):
        missing = REQUIRED_PRESCRIPTION_ITEM_KEYS - set(item.keys())
        if missing:
            raise ValueError(f"item_{idx}_missing_fields:{','.join(sorted(missing))}")
        if item.get("frequency") not in VALID_FREQUENCIES:
            raise ValueError(f"item_{idx}_invalid_frequency:{item.get('frequency')}")
        if item.get("timing") not in VALID_TIMINGS:
            raise ValueError(f"item_{idx}_invalid_timing:{item.get('timing')}")
        if item.get("route") not in VALID_ROUTES:
            raise ValueError(f"item_{idx}_invalid_route:{item.get('route')}")


@transaction.atomic
def issue_prescription(consultation_id, payload, actor_username):
    """
    payload keys:
      items             – list of Rx items (Indian format)
      doctor_qualification  – e.g. "MBBS, MD"
      doctor_reg_number     – MCI/state council reg number
      clinic_name           – optional
      clinic_address        – optional
      special_instructions  – optional footer note
      validity_days         – default 30
      patient_weight_kg     – optional (pulled from vitals if present)
    """
    consultation = Consultation.objects.get(id=consultation_id)
    if consultation.status != "FINALIZED":
        raise ValueError("consultation_not_finalized")

    items = payload.get("items", [])
    _validate_prescription_items(items)

    if hasattr(consultation, "prescription"):
        raise ValueError("prescription_already_issued")

    # Compute patient age at time of issue
    from datetime import date as _date
    patient = consultation.patient
    today = _date.today()
    age = today.year - patient.dob.year - ((today.month, today.day) < (patient.dob.month, patient.dob.day))

    # Try to pull weight from vitals if available and not provided
    weight_kg = payload.get("patient_weight_kg")
    if weight_kg is None:
        try:
            vitals = consultation.vitals
            weight_kg = vitals.weight_kg
        except Exception:
            weight_kg = None

    clinic_name = payload.get("clinic_name")
    if not clinic_name:
        clinic_name = ClinicSettings.get_solo().clinic_name

    clinic_address = payload.get("clinic_address")
    if not clinic_address:
        clinic_address = ClinicSettings.get_solo().clinic_address

    prescription = Prescription.objects.create(
        consultation=consultation,
        patient_id=consultation.patient_id,
        doctor_id=consultation.doctor_id,
        doctor_qualification=payload.get("doctor_qualification") or consultation.doctor.qualification,
        doctor_reg_number=payload.get("doctor_reg_number") or consultation.doctor.reg_number,
        clinic_name=clinic_name,
        clinic_address=clinic_address,
        items=items,
        patient_age_at_issue=age,
        patient_weight_kg=weight_kg,
        special_instructions=payload.get("special_instructions", ""),
        validity_days=payload.get("validity_days", 30),
        rx_number="",   # auto-generated by model.save()
        issued_by=actor_username,
    )

    # Once prescription is issued, the visit is considered complete.
    appointment = consultation.appointment
    if appointment.status in {"BOOKED", "RESCHEDULED"}:
        complete_appointment(appointment, actor_username)

    return prescription


@transaction.atomic
def update_prescription(consultation_id, payload, actor_username):
    consultation = Consultation.objects.get(id=consultation_id)
    if not hasattr(consultation, "prescription"):
        raise ValueError("prescription_not_found")

    prescription = consultation.prescription
    items = payload.get("items", [])
    _validate_prescription_items(items)

    prescription.items = items
    if "doctor_qualification" in payload:
        prescription.doctor_qualification = payload.get("doctor_qualification") or prescription.doctor_qualification
    if "doctor_reg_number" in payload:
        prescription.doctor_reg_number = payload.get("doctor_reg_number") or consultation.doctor.reg_number
    if "clinic_name" in payload:
        prescription.clinic_name = payload.get("clinic_name", "")
    if "clinic_address" in payload:
        prescription.clinic_address = payload.get("clinic_address", "")
    if "special_instructions" in payload:
        prescription.special_instructions = payload.get("special_instructions", "")
    if "validity_days" in payload and payload.get("validity_days"):
        prescription.validity_days = payload.get("validity_days")

    prescription.issued_by = actor_username
    prescription.save()
    return prescription



@transaction.atomic
def create_medical_order(consultation_id, order_type, description, actor_username):
    consultation = Consultation.objects.get(id=consultation_id)
    if consultation.status != "FINALIZED":
        raise ValueError("consultation_not_finalized")
    if order_type not in {"LAB", "RADIOLOGY"}:
        raise ValueError("invalid_order_type")

    order = MedicalOrder.objects.create(
        consultation=consultation,
        patient_id=consultation.patient_id,
        order_type=order_type,
        description=description,
        created_by=actor_username,
    )
    return order


@transaction.atomic
def create_medical_order_for_patient(patient_id, order_type, description, actor_username):
    consultation = (
        Consultation.objects.select_related("patient", "appointment")
        .filter(patient_id=patient_id, status="FINALIZED")
        .order_by("-finalized_at", "-created_at")
        .first()
    )
    if consultation is None:
        raise ValueError("finalized_consultation_not_found")

    order = create_medical_order(consultation.id, order_type, description, actor_username)
    return order, consultation


# ---------------------------------------------------------------------------
# Billing handoff adapter — replace this callable in tests to simulate
# success/failure without hitting a real external system.
# ---------------------------------------------------------------------------
def _default_billing_adapter(payload: dict) -> dict:
    """No-op adapter: always returns success. Override in tests."""
    return {"status": "SUCCESS", "reference": f"BL-{payload.get('consultation_id', 0):08d}"}


_billing_adapter = _default_billing_adapter

MAX_BILLING_RETRIES = 5
BACKOFF_BASE_SECONDS = 60  # 1 min * 2^attempt


def _build_billing_payload(consultation: Consultation) -> dict:
    patient = consultation.patient
    doctor = consultation.doctor
    age = None
    if patient.dob:
        from datetime import date
        today = date.today()
        age = today.year - patient.dob.year - ((today.month, today.day) < (patient.dob.month, patient.dob.day))

    gender_map = {"M": "Male", "F": "Female", "O": "Other"}

    try:
        vitals = consultation.vitals
        weight_kg = float(vitals.weight_kg) if vitals.weight_kg else None
    except Exception:
        weight_kg = None

    services = []
    for order in consultation.orders.all():
        services.append({"type": order.order_type, "description": order.description})

    try:
        rx = consultation.prescription
        services.append({"type": "PRESCRIPTION", "rx_number": rx.rx_number})
    except Exception:
        pass

    return {
        "consultation_id": consultation.id,
        "appointment_id": consultation.appointment_id,
        "mrn": patient.mrn,
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "patient_age": age,
        "patient_gender": gender_map.get(patient.gender, patient.gender),
        "patient_phone": patient.phone,
        "doctor_name": doctor.display_name,
        "doctor_specialty": doctor.specialty,
        "visit_type": consultation.appointment.visit_type,
        "diagnosis": consultation.diagnosis or "",
        "services": services,
        "finalized_at": consultation.finalized_at.isoformat() if consultation.finalized_at else None,
        "triggered_by": consultation.finalized_by or "",
    }


@transaction.atomic
def create_billing_handoff(consultation_id: int, actor_username: str) -> BillingHandoff:
    consultation = Consultation.objects.select_related("patient", "doctor", "appointment").get(id=consultation_id)
    if consultation.status != "FINALIZED":
        raise ValueError("consultation_not_finalized")
    if BillingHandoff.objects.filter(consultation_id=consultation_id).exists():
        raise ValueError("billing_handoff_already_exists")

    payload = _build_billing_payload(consultation)
    handoff = BillingHandoff.objects.create(
        consultation=consultation,
        patient=consultation.patient,
        payload=payload,
        status="PENDING",
        triggered_by=actor_username,
    )
    return handoff


@transaction.atomic
def send_billing_handoff(handoff_id: int, actor_username: str = "system") -> BillingHandoff:
    handoff = BillingHandoff.objects.select_for_update().get(id=handoff_id)

    if handoff.status == "SUCCESS":
        raise ValueError("handoff_already_succeeded")
    if handoff.status == "DEAD_LETTER":
        raise ValueError("handoff_is_dead_letter")

    attempt = handoff.retry_count + 1
    try:
        result = _billing_adapter(handoff.payload)
        outcome = "SUCCESS"
        handoff.status = "SUCCESS"
        handoff.failure_reason = ""
        handoff.next_retry_at = None
    except Exception as exc:
        outcome = "FAILED"
        failure_reason = str(exc)
        if attempt >= MAX_BILLING_RETRIES:
            handoff.status = "DEAD_LETTER"
            handoff.next_retry_at = None
        else:
            handoff.status = "FAILED"
            delay = BACKOFF_BASE_SECONDS * (2 ** attempt)
            handoff.next_retry_at = timezone.now() + timedelta(seconds=delay)
        handoff.failure_reason = failure_reason
        result = None

    handoff.retry_count = attempt
    handoff.save()

    BillingRetryLog.objects.create(
        handoff=handoff,
        attempt_number=attempt,
        outcome=outcome,
        failure_reason=handoff.failure_reason,
        actor_username=actor_username,
    )

    return handoff


def list_billing_handoffs(status: str = None, date_from: str = None, date_to: str = None) -> list:
    qs = BillingHandoff.objects.select_related("consultation", "patient").all()
    if status:
        qs = qs.filter(status=status)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return list(qs)


# ---------------------------------------------------------------------------
# Sprint 1 Billing foundation (BM-1.1 to BM-1.4)
# ---------------------------------------------------------------------------

def _resolve_appointment_for_opd(opd_number: str, appointment_id=None):
    normalized_opd = (opd_number or "").strip()

    if appointment_id:
        appointment = Appointment.objects.select_related("patient", "doctor").get(id=appointment_id)
        valid_opd_numbers = {
            (appointment.opd_number or "").strip(),
            (appointment.patient.opd_number or "").strip(),
        }
        if normalized_opd not in valid_opd_numbers:
            raise ValueError("opd_number_mismatch")
        return appointment

    appointment = (
        Appointment.objects
        .select_related("patient", "doctor")
        .filter(opd_number=normalized_opd)
        .first()
    )
    if appointment:
        return appointment

    patient = Patient.objects.filter(opd_number=normalized_opd).first()
    if patient is None:
        return None

    return (
        Appointment.objects
        .select_related("patient", "doctor")
        .filter(patient_id=patient.id)
        .exclude(status="CANCELLED")
        .order_by("-created_at")
        .first()
    )


@transaction.atomic
def create_or_get_active_billing_ledger(opd_number, actor_username, appointment_id=None):
    if not opd_number:
        raise ValueError("opd_number_required")

    existing = BillingLedger.objects.select_for_update().filter(opd_number=opd_number).first()
    if existing:
        return existing, False

    appointment = _resolve_appointment_for_opd(opd_number, appointment_id=appointment_id)
    if appointment is None:
        raise ValueError("appointment_not_found")

    ledger = BillingLedger.objects.create(
        opd_number=opd_number,
        appointment=appointment,
        patient=appointment.patient,
        doctor=appointment.doctor,
        visit_date=appointment.slot_date,
        visit_type=appointment.visit_type,
        status="OPEN",
        created_by=actor_username,
        updated_by=actor_username,
    )
    BillingAuditEvent.objects.create(
        ledger=ledger,
        action="LEDGER_CREATED",
        actor_username=actor_username,
        payload={"opd_number": opd_number, "appointment_id": appointment.id},
    )
    return ledger, True


@transaction.atomic
def add_billing_line_item(ledger_id, line_type, amount, actor_username, description="", source_order_id=""):
    ledger = BillingLedger.objects.select_for_update().get(id=ledger_id)

    if line_type not in {"OPD_NEW_FEE", "OPD_REPEAT_FEE", "MANUAL"}:
        raise ValueError("invalid_line_type")

    if ledger.status == "FINALIZED":
        if line_type != "MANUAL":
            raise ValueError("ledger_finalized")
        ledger.status = "OPEN"
        ledger.finalized_by = ""
        ledger.finalized_at = None
        ledger.updated_by = actor_username
        ledger.save(update_fields=["status", "finalized_by", "finalized_at", "updated_by", "updated_at"])
        BillingAuditEvent.objects.create(
            ledger=ledger,
            action="LEDGER_REOPENED",
            actor_username=actor_username,
            payload={"reason": "additional_manual_charges"},
        )

    amount_decimal = Decimal(str(amount))
    if amount_decimal <= Decimal("0"):
        raise ValueError("invalid_amount")

    # Keep one mandatory OPD new fee line by default to avoid accidental duplicates.
    if line_type == "OPD_NEW_FEE":
        duplicate = BillingLineItem.objects.filter(ledger=ledger, line_type="OPD_NEW_FEE").first()
        if duplicate:
            raise ValueError("opd_new_fee_already_present")

    item = BillingLineItem.objects.create(
        ledger=ledger,
        line_type=line_type,
        description=description or "",
        amount=amount_decimal,
        source_order_id=source_order_id or "",
        created_by=actor_username,
    )
    ledger.updated_by = actor_username
    ledger.save(update_fields=["updated_by", "updated_at"])
    return item


@transaction.atomic
def set_repeat_fee_decision(ledger_id, decision, actor_username, reason="", amount=None):
    ledger = BillingLedger.objects.select_for_update().get(id=ledger_id)
    if ledger.status == "FINALIZED":
        raise ValueError("ledger_finalized")

    if decision not in {"YES", "NO"}:
        raise ValueError("invalid_repeat_fee_decision")

    if decision == "NO":
        if not reason.strip():
            raise ValueError("repeat_fee_reason_required")
        BillingLineItem.objects.filter(ledger=ledger, line_type="OPD_REPEAT_FEE").delete()
        ledger.repeat_fee_decision = "NO"
        ledger.repeat_fee_reason = reason.strip()
    else:
        if amount is None:
            raise ValueError("repeat_fee_amount_required")
        amount_decimal = Decimal(str(amount))
        if amount_decimal <= Decimal("0"):
            raise ValueError("invalid_amount")
        repeat_item = BillingLineItem.objects.filter(ledger=ledger, line_type="OPD_REPEAT_FEE").first()
        if repeat_item:
            repeat_item.amount = amount_decimal
            repeat_item.description = "Repeat OPD consultation fee"
            repeat_item.created_by = actor_username
            repeat_item.save(update_fields=["amount", "description", "created_by"])
        else:
            BillingLineItem.objects.create(
                ledger=ledger,
                line_type="OPD_REPEAT_FEE",
                description="Repeat OPD consultation fee",
                amount=amount_decimal,
                created_by=actor_username,
            )
        ledger.repeat_fee_decision = "YES"
        ledger.repeat_fee_reason = ""

    ledger.updated_by = actor_username
    ledger.save(update_fields=["repeat_fee_decision", "repeat_fee_reason", "updated_by", "updated_at"])
    BillingAuditEvent.objects.create(
        ledger=ledger,
        action="REPEAT_FEE_DECISION",
        actor_username=actor_username,
        payload={"decision": decision, "reason": reason or "", "amount": str(amount) if amount is not None else None},
    )
    return ledger


def _billing_subtotal(ledger):
    total = Decimal("0")
    for line in ledger.line_items.all():
        total += Decimal(str(line.amount))
    return total


@transaction.atomic
def finalize_billing_ledger(ledger_id, actor_username, tax=0, discount=0):
    ledger = BillingLedger.objects.select_for_update().get(id=ledger_id)
    if ledger.status == "FINALIZED":
        raise ValueError("already_finalized")

    if ledger.visit_type == "NEW":
        has_new_fee = BillingLineItem.objects.filter(ledger=ledger, line_type="OPD_NEW_FEE").exists()
        if not has_new_fee:
            raise ValueError("mandatory_new_opd_fee_missing")

    if ledger.visit_type == "FOLLOW_UP" and ledger.repeat_fee_decision == "NO" and not ledger.repeat_fee_reason.strip():
        raise ValueError("repeat_fee_reason_required")

    subtotal = _billing_subtotal(ledger)
    tax_decimal = Decimal(str(tax or 0))
    discount_decimal = Decimal(str(discount or 0))
    if tax_decimal < 0 or discount_decimal < 0:
        raise ValueError("invalid_tax_or_discount")

    total = subtotal + tax_decimal - discount_decimal
    if total < 0:
        raise ValueError("invalid_total")

    invoice, _ = BillingInvoice.objects.get_or_create(
        ledger=ledger,
        defaults={
            "subtotal": subtotal,
            "discount": discount_decimal,
            "tax": tax_decimal,
            "total": total,
            "created_by": actor_username,
        },
    )
    if invoice.total != total or invoice.subtotal != subtotal or invoice.tax != tax_decimal or invoice.discount != discount_decimal:
        invoice.subtotal = subtotal
        invoice.discount = discount_decimal
        invoice.tax = tax_decimal
        invoice.total = total
        invoice.save(update_fields=["subtotal", "discount", "tax", "total"])

    ledger.status = "FINALIZED"
    ledger.finalized_by = actor_username
    ledger.finalized_at = timezone.now()
    ledger.updated_by = actor_username
    ledger.save(update_fields=["status", "finalized_by", "finalized_at", "updated_by", "updated_at"])
    BillingAuditEvent.objects.create(
        ledger=ledger,
        action="LEDGER_FINALIZED",
        actor_username=actor_username,
        payload={"invoice_id": invoice.id, "bill_number": invoice.bill_number},
    )
    return ledger, invoice


# ---------------------------------------------------------------------------
# Story 5.1 – Daily OPD KPI dashboard
# ---------------------------------------------------------------------------

def daily_kpi_metrics(report_date, specialty=None, doctor_id=None, location=None):
    """
    Returns daily operational KPIs for OPD.
    location is accepted for contract compatibility (single-site MVP currently).
    """
    appointment_qs = Appointment.objects.select_related("doctor").filter(slot_date=report_date)
    slot_qs = DoctorSlot.objects.select_related("doctor").filter(slot_date=report_date, status="AVAILABLE")
    queue_qs = QueueItem.objects.select_related("doctor", "appointment").filter(slot_date=report_date)

    if specialty:
        appointment_qs = appointment_qs.filter(doctor__specialty=specialty)
        slot_qs = slot_qs.filter(doctor__specialty=specialty)
        queue_qs = queue_qs.filter(doctor__specialty=specialty)

    if doctor_id:
        appointment_qs = appointment_qs.filter(doctor_id=doctor_id)
        slot_qs = slot_qs.filter(doctor_id=doctor_id)
        queue_qs = queue_qs.filter(doctor_id=doctor_id)

    total_appointments = appointment_qs.exclude(status="CANCELLED").count()
    completed_appointments = appointment_qs.filter(status="COMPLETED").count()

    total_slots = slot_qs.count()
    utilization_pct = round((completed_appointments / total_slots) * 100, 2) if total_slots else 0.0

    total_queue_items = queue_qs.count()
    no_show_count = queue_qs.filter(status="NO_SHOW").count()
    no_show_rate_pct = round((no_show_count / total_queue_items) * 100, 2) if total_queue_items else 0.0

    called_items = queue_qs.filter(called_at__isnull=False)
    wait_samples = []
    for item in called_items:
        if item.called_at and item.appointment and item.appointment.created_at:
            delta = item.called_at - item.appointment.created_at
            wait_samples.append(max(delta.total_seconds() / 60.0, 0.0))
    avg_wait_minutes = round(sum(wait_samples) / len(wait_samples), 2) if wait_samples else 0.0

    return {
        "date": str(report_date),
        "filters": {
            "specialty": specialty or "ALL",
            "doctor_id": int(doctor_id) if doctor_id else None,
            "location": location or "MAIN_OPD",
        },
        "metrics": {
            "volume": total_appointments,
            "completed": completed_appointments,
            "wait_time_avg_minutes": avg_wait_minutes,
            "no_show_count": no_show_count,
            "no_show_rate_pct": no_show_rate_pct,
            "utilization_pct": utilization_pct,
        },
    }


def _render_csv_report(kpi_payload):
    import csv
    from io import StringIO

    rows = [
        ["date", kpi_payload["date"]],
        ["specialty", kpi_payload["filters"]["specialty"]],
        ["doctor_id", kpi_payload["filters"]["doctor_id"]],
        ["location", kpi_payload["filters"]["location"]],
        [],
        ["metric", "value"],
    ]
    for key, value in kpi_payload["metrics"].items():
        rows.append([key, value])

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return buffer.getvalue()


def _render_pdf_like_report(kpi_payload):
    # Lightweight text payload persisted as PDF artifact content for MVP export.
    lines = [
        "OPD Daily KPI Report",
        f"Date: {kpi_payload['date']}",
        f"Specialty: {kpi_payload['filters']['specialty']}",
        f"Doctor ID: {kpi_payload['filters']['doctor_id']}",
        f"Location: {kpi_payload['filters']['location']}",
        "",
        "Metrics:",
    ]
    for key, value in kpi_payload["metrics"].items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def generate_report_export(export_format, filters, actor_username):
    if export_format not in {"CSV", "PDF"}:
        raise ValueError("invalid_export_format")

    report_date = filters.get("date")
    specialty = filters.get("specialty")
    doctor_id = filters.get("doctor_id")
    location = filters.get("location")

    if report_date:
        report_date_obj = datetime.strptime(report_date, "%Y-%m-%d").date()
    else:
        report_date_obj = timezone.localdate()

    kpi_payload = daily_kpi_metrics(
        report_date=report_date_obj,
        specialty=specialty,
        doctor_id=doctor_id,
        location=location,
    )

    if export_format == "CSV":
        content = _render_csv_report(kpi_payload)
        ext = "csv"
    else:
        content = _render_pdf_like_report(kpi_payload)
        ext = "pdf"

    export = ReportExport.objects.create(
        requested_by=actor_username,
        format=export_format,
        filters={**filters, "date": str(report_date_obj)},
        artifact_name=f"opd-report-{report_date_obj}.{ext}",
        artifact_content=content,
        status="GENERATED",
    )

    ReportExportAudit.objects.create(
        report_export=export,
        action="GENERATE",
        actor_username=actor_username,
        payload={"format": export_format, "filters": export.filters},
    )
    return export


def download_report_export(export_id, actor_username):
    export = ReportExport.objects.get(id=export_id)
    export.download_count += 1
    export.last_downloaded_at = timezone.now()
    export.save(update_fields=["download_count", "last_downloaded_at"])

    ReportExportAudit.objects.create(
        report_export=export,
        action="DOWNLOAD",
        actor_username=actor_username,
        payload={"format": export.format, "artifact_name": export.artifact_name},
    )
    return export


# ---------------------------------------------------------------------------
# Story 5.3 – Observability alerts and incident records
# ---------------------------------------------------------------------------

def evaluate_alert_rules(queue_lag, billing_backlog, queue_lag_threshold, billing_backlog_threshold):
    alerts = []
    if queue_lag >= queue_lag_threshold:
        severity = "CRITICAL" if queue_lag >= (queue_lag_threshold * 2) else "WARN"
        alerts.append(
            {
                "metric_name": "queue_lag",
                "observed_value": float(queue_lag),
                "threshold_value": float(queue_lag_threshold),
                "severity": severity,
                "message": f"Queue lag breached threshold: {queue_lag}",
            }
        )
    if billing_backlog >= billing_backlog_threshold:
        severity = "CRITICAL" if billing_backlog >= (billing_backlog_threshold * 2) else "WARN"
        alerts.append(
            {
                "metric_name": "billing_backlog",
                "observed_value": float(billing_backlog),
                "threshold_value": float(billing_backlog_threshold),
                "severity": severity,
                "message": f"Billing backlog breached threshold: {billing_backlog}",
            }
        )
    return alerts


def observability_snapshot(actor_username="system", queue_lag_threshold=25, billing_backlog_threshold=10):
    queue_lag = QueueItem.objects.filter(status__in=["WAITING", "SKIPPED"]).count()
    billing_backlog = BillingHandoff.objects.filter(status__in=["PENDING", "FAILED", "DEAD_LETTER"]).count()

    alerts = evaluate_alert_rules(
        queue_lag=queue_lag,
        billing_backlog=billing_backlog,
        queue_lag_threshold=queue_lag_threshold,
        billing_backlog_threshold=billing_backlog_threshold,
    )

    for alert in alerts:
        alert_event = AlertEvent.objects.create(
            metric_name=alert["metric_name"],
            observed_value=alert["observed_value"],
            threshold_value=alert["threshold_value"],
            severity=alert["severity"],
            message=alert["message"],
            context={"actor": actor_username},
        )
        if alert_event.severity == "CRITICAL":
            IncidentRecord.objects.create(
                severity="CRITICAL",
                source=alert_event.metric_name,
                summary=alert_event.message,
                runbook_ref="runbooks/opd-incident-response.md",
                details={"alert_event_id": alert_event.id, "actor": actor_username},
                created_by=actor_username,
            )

    open_incidents = IncidentRecord.objects.filter(status="OPEN").count()
    return {
        "metrics": {
            "queue_lag": queue_lag,
            "billing_backlog": billing_backlog,
            "open_incidents": open_incidents,
        },
        "alerts": alerts,
    }


def create_incident_record(severity, source, summary, runbook_ref, details, actor_username):
    if severity not in {"INFO", "WARN", "CRITICAL"}:
        raise ValueError("invalid_severity")
    incident = IncidentRecord.objects.create(
        severity=severity,
        source=source,
        summary=summary,
        runbook_ref=runbook_ref or "",
        details=details or {},
        created_by=actor_username,
    )
    return incident


def resolve_incident_record(incident_id, actor_username):
    incident = IncidentRecord.objects.get(id=incident_id)
    if incident.status == "RESOLVED":
        raise ValueError("already_resolved")
    incident.status = "RESOLVED"
    incident.resolved_by = actor_username
    incident.resolved_at = timezone.now()
    incident.save(update_fields=["status", "resolved_by", "resolved_at"])
    return incident

