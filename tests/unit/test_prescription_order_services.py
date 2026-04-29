import datetime

import pytest

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient
from apps.core.services import (
    create_medical_order,
    create_or_update_consultation_draft,
    finalize_consultation,
    issue_prescription,
)


pytestmark = pytest.mark.django_db


def _seed_finalized_consultation():
    patient = Patient.objects.create(
        first_name="Raj", last_name="Rx",
        dob=datetime.date(1982, 4, 10), gender="M", phone="9800000001",
    )
    doctor = Doctor.objects.create(full_name="Dr. Rx", specialty="General Medicine")
    slot_date = datetime.date(2026, 5, 15)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(9, 0), end_time=datetime.time(9, 10))
    appt = Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(9, 0), end_time=datetime.time(9, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )
    c = create_or_update_consultation_draft(appt.id, {"diagnosis": "Hypertension"}, "dr_rx")
    return finalize_consultation(c.id, "dr_rx")


# Indian-format Rx item with all required fields
VALID_INDIAN_ITEMS = [
    {
        "drug": "Amlodipine",
        "dosage_form": "Tablet",
        "strength": "5mg",
        "dose": "1 tablet",
        "frequency": "OD",
        "duration": "30 days",
        "timing": "after_food",
        "route": "oral",
        "instructions": "Take with water after dinner",
    }
]

VALID_PAYLOAD = {
    "items": VALID_INDIAN_ITEMS,
    "doctor_qualification": "MBBS, MD (Medicine)",
    "doctor_reg_number": "MH-12345",
    "clinic_name": "City OPD Clinic",
    "clinic_address": "123, MG Road, Pune, Maharashtra - 411001",
    "special_instructions": "Avoid alcohol. Monitor BP weekly.",
    "validity_days": 30,
}


def test_issue_prescription_stores_indian_format_items():
    consultation = _seed_finalized_consultation()

    prescription = issue_prescription(consultation.id, VALID_PAYLOAD, "dr_rx")

    assert prescription.items[0]["drug"] == "Amlodipine"
    assert prescription.items[0]["frequency"] == "OD"
    assert prescription.items[0]["timing"] == "after_food"
    assert prescription.items[0]["route"] == "oral"
    assert prescription.doctor_qualification == "MBBS, MD (Medicine)"
    assert prescription.doctor_reg_number == "MH-12345"
    assert prescription.clinic_name == "City OPD Clinic"
    assert prescription.rx_number.startswith("RX-")
    assert prescription.validity_days == 30


def test_issue_prescription_auto_fills_patient_age():
    consultation = _seed_finalized_consultation()

    prescription = issue_prescription(consultation.id, VALID_PAYLOAD, "dr_rx")

    assert prescription.patient_age_at_issue is not None
    assert prescription.patient_age_at_issue > 0


def test_issue_prescription_twice_raises_error():
    consultation = _seed_finalized_consultation()
    issue_prescription(consultation.id, VALID_PAYLOAD, "dr_rx")

    with pytest.raises(ValueError, match="prescription_already_issued"):
        issue_prescription(consultation.id, VALID_PAYLOAD, "dr_rx")


def test_issue_prescription_requires_finalized_consultation():
    patient = Patient.objects.create(
        first_name="Draft", last_name="Only2",
        dob=datetime.date(1991, 1, 1), gender="M", phone="9800000002",
    )
    doctor = Doctor.objects.create(full_name="Dr. Draft2", specialty="General")
    slot_date = datetime.date(2026, 5, 16)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(10, 0), end_time=datetime.time(10, 10))
    appt = Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(10, 0), end_time=datetime.time(10, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )
    draft = create_or_update_consultation_draft(appt.id, {"notes": "draft"}, "dr_rx")

    with pytest.raises(ValueError, match="consultation_not_finalized"):
        issue_prescription(draft.id, VALID_PAYLOAD, "dr_rx")


def test_missing_required_item_field_raises_error():
    consultation = _seed_finalized_consultation()
    # Missing 'timing' and 'route'
    bad_items = [{"drug": "Aspirin", "dosage_form": "Tablet", "strength": "75mg", "dose": "1", "frequency": "OD", "duration": "7 days"}]

    with pytest.raises(ValueError, match="missing_fields"):
        issue_prescription(consultation.id, {"items": bad_items}, "dr_rx")


def test_invalid_frequency_raises_error():
    consultation = _seed_finalized_consultation()
    bad_items = [{**VALID_INDIAN_ITEMS[0], "frequency": "TWICE_DAILY"}]

    with pytest.raises(ValueError, match="invalid_frequency"):
        issue_prescription(consultation.id, {"items": bad_items}, "dr_rx")


def test_create_lab_order():
    consultation = _seed_finalized_consultation()
    order = create_medical_order(consultation.id, "LAB", "CBC and Lipid Panel", "dr_rx")
    assert order.order_type == "LAB"
    assert order.status == "PENDING"


def test_create_radiology_order():
    consultation = _seed_finalized_consultation()
    order = create_medical_order(consultation.id, "RADIOLOGY", "Chest X-Ray PA View", "dr_rx")
    assert order.order_type == "RADIOLOGY"


def test_invalid_order_type_raises_error():
    consultation = _seed_finalized_consultation()
    with pytest.raises(ValueError, match="invalid_order_type"):
        create_medical_order(consultation.id, "SURGERY", "Remove appendix", "dr_rx")
