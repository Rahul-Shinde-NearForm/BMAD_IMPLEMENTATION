import datetime

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient


pytestmark = pytest.mark.django_db


def _doctor_user():
    user = User.objects.create_user(username="dr_endpoint", password="pass1234")
    group, _ = Group.objects.get_or_create(name="Doctor")
    user.groups.add(group)
    return user


def _seed_appointment():
    patient = Patient.objects.create(
        first_name="Aarav",
        last_name="Visit",
        dob=datetime.date(1985, 7, 12),
        gender="M",
        phone="9500000001",
    )
    doctor = Doctor.objects.create(full_name="Dr. Endpoint", specialty="General")
    slot_date = datetime.date(2026, 5, 11)
    DoctorSlot.objects.create(
        doctor=doctor,
        slot_date=slot_date,
        start_time=datetime.time(10, 0),
        end_time=datetime.time(10, 10),
    )
    appointment = Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        slot_date=slot_date,
        start_time=datetime.time(10, 0),
        end_time=datetime.time(10, 10),
        visit_type="NEW",
        channel="WALK_IN",
        status="BOOKED",
    )
    return appointment


def test_doctor_can_save_draft(client):
    user = _doctor_user()
    client.force_login(user)
    appointment = _seed_appointment()

    response = client.post(
        f"/api/consultations/appointment/{appointment.id}/draft/",
        {"chief_complaint": "Sore throat", "diagnosis": "Pharyngitis"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "DRAFT"
    assert "consultation_id" in data


def test_save_draft_is_idempotent(client):
    user = _doctor_user()
    client.force_login(user)
    appointment = _seed_appointment()

    client.post(
        f"/api/consultations/appointment/{appointment.id}/draft/",
        {"chief_complaint": "Headache"},
    )
    second = client.post(
        f"/api/consultations/appointment/{appointment.id}/draft/",
        {"findings": "No signs"},
    )

    assert second.status_code == 200
    get_resp = client.get(f"/api/consultations/appointment/{appointment.id}/")
    body = get_resp.json()
    assert body["chief_complaint"] == "Headache"
    assert body["findings"] == "No signs"


def test_doctor_can_finalize_consultation(client):
    user = _doctor_user()
    client.force_login(user)
    appointment = _seed_appointment()

    draft_resp = client.post(
        f"/api/consultations/appointment/{appointment.id}/draft/",
        {"chief_complaint": "Cough", "diagnosis": "Bronchitis"},
    )
    consultation_id = draft_resp.json()["consultation_id"]

    fin_resp = client.post(f"/api/consultations/{consultation_id}/finalize/")

    assert fin_resp.status_code == 200
    assert fin_resp.json()["status"] == "FINALIZED"
    assert fin_resp.json()["finalized_by"] == "dr_endpoint"


def test_edit_blocked_after_finalization(client):
    user = _doctor_user()
    client.force_login(user)
    appointment = _seed_appointment()

    draft_resp = client.post(
        f"/api/consultations/appointment/{appointment.id}/draft/",
        {"notes": "Initial"},
    )
    consultation_id = draft_resp.json()["consultation_id"]
    client.post(f"/api/consultations/{consultation_id}/finalize/")

    blocked = client.post(
        f"/api/consultations/appointment/{appointment.id}/draft/",
        {"notes": "Tampered"},
    )

    assert blocked.status_code == 409
    assert blocked.json()["error"] == "already_finalized"


def test_receptionist_cannot_save_draft(client):
    user = User.objects.create_user(username="recv_consult", password="pass1234")
    group, _ = Group.objects.get_or_create(name="Receptionist")
    user.groups.add(group)
    client.force_login(user)
    appointment = _seed_appointment()

    response = client.post(
        f"/api/consultations/appointment/{appointment.id}/draft/",
        {"chief_complaint": "test"},
    )
    assert response.status_code == 403
