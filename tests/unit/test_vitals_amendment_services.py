import datetime

import pytest

from apps.core.models import Appointment, Consultation, Doctor, DoctorSlot, Patient, Vitals
from apps.core.services import amend_consultation, create_or_update_consultation_draft, finalize_consultation, record_vitals


pytestmark = pytest.mark.django_db


def _seed_finalized_consultation():
    patient = Patient.objects.create(
        first_name="Tara",
        last_name="Amend",
        dob=datetime.date(1990, 3, 15),
        gender="F",
        phone="9600000001",
    )
    doctor = Doctor.objects.create(full_name="Dr. Amend", specialty="General")
    slot_date = datetime.date(2026, 5, 12)
    DoctorSlot.objects.create(
        doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(9, 0), end_time=datetime.time(9, 10),
    )
    appointment = Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(9, 0), end_time=datetime.time(9, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )
    consultation = create_or_update_consultation_draft(
        appointment.id, {"chief_complaint": "Cough", "diagnosis": "Bronchitis"}, "dr_user"
    )
    finalized = finalize_consultation(consultation.id, "dr_user")
    return finalized


def test_record_vitals_stores_values():
    consultation = _seed_finalized_consultation()

    vitals = record_vitals(
        consultation.id,
        {"pulse_bpm": 72, "bp_systolic": 120, "bp_diastolic": 80, "spo2_pct": 98},
        "nurse_user",
    )

    assert vitals.pulse_bpm == 72
    assert vitals.spo2_pct == 98
    assert vitals.recorded_by == "nurse_user"


def test_record_vitals_is_upsert():
    consultation = _seed_finalized_consultation()
    record_vitals(consultation.id, {"pulse_bpm": 70}, "nurse_user")
    updated = record_vitals(consultation.id, {"pulse_bpm": 80, "weight_kg": "65.5"}, "nurse_user")

    assert updated.pulse_bpm == 80
    assert Vitals.objects.filter(consultation=consultation).count() == 1


def test_amend_finalized_consultation_writes_audit():
    consultation = _seed_finalized_consultation()

    amendment = amend_consultation(
        consultation.id, "diagnosis", "Asthma", "Corrected after review", "dr_user"
    )

    consultation.refresh_from_db()
    assert consultation.diagnosis == "Asthma"
    assert amendment.previous_value == "Bronchitis"
    assert amendment.reason == "Corrected after review"


def test_amend_draft_raises_not_finalized():
    patient = Patient.objects.create(
        first_name="Draft",
        last_name="Only",
        dob=datetime.date(1991, 1, 1),
        gender="M",
        phone="9600000002",
    )
    doctor = Doctor.objects.create(full_name="Dr. Draft", specialty="General")
    slot_date = datetime.date(2026, 5, 13)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(10, 0), end_time=datetime.time(10, 10))
    appointment = Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(10, 0), end_time=datetime.time(10, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )
    consultation = create_or_update_consultation_draft(appointment.id, {"notes": "draft"}, "dr_user")

    with pytest.raises(ValueError, match="not_finalized"):
        amend_consultation(consultation.id, "notes", "new notes", "reason", "dr_user")


def test_amend_invalid_field_raises_error():
    consultation = _seed_finalized_consultation()

    with pytest.raises(ValueError, match="invalid_field"):
        amend_consultation(consultation.id, "status", "DRAFT", "hack attempt", "dr_user")
