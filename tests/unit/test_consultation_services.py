import datetime

import pytest

from apps.core.models import Appointment, Consultation, Doctor, DoctorSlot, Patient
from apps.core.services import create_or_update_consultation_draft, finalize_consultation


pytestmark = pytest.mark.django_db


def _seed_appointment():
    patient = Patient.objects.create(
        first_name="Priya",
        last_name="Consult",
        dob=datetime.date(1988, 5, 1),
        gender="F",
        phone="9400000001",
    )
    doctor = Doctor.objects.create(full_name="Dr. Notes", specialty="General")
    slot_date = datetime.date(2026, 5, 10)
    DoctorSlot.objects.create(
        doctor=doctor,
        slot_date=slot_date,
        start_time=datetime.time(9, 0),
        end_time=datetime.time(9, 10),
    )
    appointment = Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        slot_date=slot_date,
        start_time=datetime.time(9, 0),
        end_time=datetime.time(9, 10),
        visit_type="NEW",
        channel="WALK_IN",
        status="BOOKED",
    )
    return appointment


def test_create_draft_creates_consultation():
    appointment = _seed_appointment()

    consultation = create_or_update_consultation_draft(
        appointment.id,
        {"chief_complaint": "Fever", "diagnosis": "Viral"},
        "dr_user",
    )

    assert consultation.status == "DRAFT"
    assert consultation.chief_complaint == "Fever"
    assert consultation.diagnosis == "Viral"


def test_update_draft_merges_fields():
    appointment = _seed_appointment()
    create_or_update_consultation_draft(appointment.id, {"chief_complaint": "Cough"}, "dr_user")

    updated = create_or_update_consultation_draft(appointment.id, {"findings": "Lungs clear"}, "dr_user")

    assert updated.chief_complaint == "Cough"
    assert updated.findings == "Lungs clear"


def test_finalize_locks_consultation():
    appointment = _seed_appointment()
    consultation = create_or_update_consultation_draft(
        appointment.id, {"chief_complaint": "Headache"}, "dr_user"
    )

    finalized = finalize_consultation(consultation.id, "dr_user")

    assert finalized.status == "FINALIZED"
    assert finalized.finalized_by == "dr_user"
    assert finalized.finalized_at is not None


def test_draft_edit_blocked_after_finalization():
    appointment = _seed_appointment()
    consultation = create_or_update_consultation_draft(appointment.id, {"notes": "OK"}, "dr_user")
    finalize_consultation(consultation.id, "dr_user")

    with pytest.raises(ValueError, match="already_finalized"):
        create_or_update_consultation_draft(appointment.id, {"notes": "changed"}, "dr_user")


def test_double_finalize_raises_error():
    appointment = _seed_appointment()
    consultation = create_or_update_consultation_draft(appointment.id, {"notes": "OK"}, "dr_user")
    finalize_consultation(consultation.id, "dr_user")

    with pytest.raises(ValueError, match="already_finalized"):
        finalize_consultation(consultation.id, "dr_user")
