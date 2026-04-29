import datetime

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient
from apps.core.services import create_or_update_consultation_draft, finalize_consultation


pytestmark = pytest.mark.django_db


def _user_with_role(username, role):
    user = User.objects.create_user(username=username, password="pass1234")
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


def _seed_appointment():
    patient = Patient.objects.create(
        first_name="Kiran",
        last_name="Vitals",
        dob=datetime.date(1985, 9, 20),
        gender="M",
        phone="9700000001",
    )
    doctor = Doctor.objects.create(full_name="Dr. Vitals", specialty="General")
    slot_date = datetime.date(2026, 5, 14)
    DoctorSlot.objects.create(
        doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(11, 0), end_time=datetime.time(11, 10),
    )
    return Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(11, 0), end_time=datetime.time(11, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )


def _finalized_consultation(appointment):
    c = create_or_update_consultation_draft(appointment.id, {"chief_complaint": "Pain", "diagnosis": "Sprain"}, "dr_user")
    return finalize_consultation(c.id, "dr_user")


def test_receptionist_can_record_vitals(client):
    user = _user_with_role("nurse_v", "Receptionist")
    client.force_login(user)
    appointment = _seed_appointment()
    consultation = _finalized_consultation(appointment)

    response = client.post(
        f"/api/consultations/{consultation.id}/vitals/",
        {"pulse_bpm": 75, "bp_systolic": 118, "bp_diastolic": 76, "spo2_pct": 99},
    )

    assert response.status_code == 200
    assert "vitals_id" in response.json()


def test_doctor_can_amend_finalized_consultation(client):
    user = _user_with_role("dr_amend_ep", "Doctor")
    client.force_login(user)
    appointment = _seed_appointment()
    consultation = _finalized_consultation(appointment)

    response = client.post(
        f"/api/consultations/{consultation.id}/amend/",
        {"field_name": "diagnosis", "new_value": "Fracture", "reason": "Radiograph confirmed"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["field_name"] == "diagnosis"
    assert data["new_value"] == "Fracture"
    assert data["previous_value"] == "Sprain"


def test_amendment_history_returns_audit_trail(client):
    user = _user_with_role("dr_hist", "Doctor")
    client.force_login(user)
    appointment = _seed_appointment()
    consultation = _finalized_consultation(appointment)
    client.post(
        f"/api/consultations/{consultation.id}/amend/",
        {"field_name": "notes", "new_value": "Updated notes", "reason": "Clarification"},
    )

    response = client.get(f"/api/consultations/{consultation.id}/amendments/")

    assert response.status_code == 200
    amendments = response.json()["amendments"]
    assert len(amendments) == 1
    assert amendments[0]["reason"] == "Clarification"


def test_amend_draft_returns_conflict(client):
    user = _user_with_role("dr_conflict", "Doctor")
    client.force_login(user)
    appointment = _seed_appointment()
    draft = create_or_update_consultation_draft(appointment.id, {"notes": "draft"}, "dr_user")

    response = client.post(
        f"/api/consultations/{draft.id}/amend/",
        {"field_name": "notes", "new_value": "changed", "reason": "test"},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "not_finalized"
