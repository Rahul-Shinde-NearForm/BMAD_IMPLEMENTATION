import datetime

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient


pytestmark = pytest.mark.django_db


def _user_with_role(username, role):
    user = User.objects.create_user(username=username, password="pass1234")
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


def _seed_dashboard_data():
    doctor = Doctor.objects.create(full_name="Dr Dash", specialty="General Medicine")
    slot_date = datetime.date(2026, 5, 4)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(9, 0), end_time=datetime.time(9, 10))
    patient = Patient.objects.create(first_name="Dash", last_name="Pat", dob=datetime.date(1990, 1, 1), gender="M", phone="9111111111")
    Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(9, 0), end_time=datetime.time(9, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )
    return doctor, slot_date


def test_admin_can_view_daily_dashboard_metrics(client):
    admin = _user_with_role("admin_dash", "Admin")
    doctor, slot_date = _seed_dashboard_data()
    client.force_login(admin)

    response = client.get(f"/api/reports/dashboard/daily-metrics/?date={slot_date}&doctor_id={doctor.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["date"] == str(slot_date)
    assert payload["metrics"]["volume"] == 1


def test_receptionist_cannot_view_daily_dashboard_metrics(client):
    rec = _user_with_role("rec_dash", "Receptionist")
    doctor, slot_date = _seed_dashboard_data()
    client.force_login(rec)

    response = client.get(f"/api/reports/dashboard/daily-metrics/?date={slot_date}&doctor_id={doctor.id}")

    assert response.status_code == 403


def test_invalid_date_returns_400(client):
    admin = _user_with_role("admin_dash2", "Admin")
    client.force_login(admin)

    response = client.get("/api/reports/dashboard/daily-metrics/?date=2026-99-99")

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_date_format"
