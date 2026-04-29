import datetime
import json

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient


pytestmark = pytest.mark.django_db


def _user_with_role(username, role):
    user = User.objects.create_user(username=username, password="pass1234")
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


def _seed_report_data():
    doctor = Doctor.objects.create(full_name="Dr Endpoint", specialty="General Medicine")
    slot_date = datetime.date(2026, 5, 6)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(11, 0), end_time=datetime.time(11, 10))
    patient = Patient.objects.create(first_name="End", last_name="Point", dob=datetime.date(1990, 1, 1), gender="F", phone="9888888888")
    Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        slot_date=slot_date,
        start_time=datetime.time(11, 0),
        end_time=datetime.time(11, 10),
        visit_type="NEW",
        channel="WALK_IN",
        status="BOOKED",
    )
    return slot_date


def test_admin_can_generate_export(client):
    admin = _user_with_role("admin_export", "Admin")
    report_date = _seed_report_data()
    client.force_login(admin)

    response = client.post(
        "/api/reports/exports/generate/",
        data=json.dumps({"format": "CSV", "filters": {"date": str(report_date)}}),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["format"] == "CSV"
    assert data["artifact_name"].endswith(".csv")


def test_non_admin_cannot_generate_export(client):
    doctor = _user_with_role("doctor_export", "Doctor")
    client.force_login(doctor)

    response = client.post(
        "/api/reports/exports/generate/",
        data=json.dumps({"format": "CSV", "filters": {}}),
        content_type="application/json",
    )

    assert response.status_code == 403


def test_admin_can_download_export(client):
    admin = _user_with_role("admin_download", "Admin")
    report_date = _seed_report_data()
    client.force_login(admin)

    generated = client.post(
        "/api/reports/exports/generate/",
        data=json.dumps({"format": "CSV", "filters": {"date": str(report_date)}}),
        content_type="application/json",
    ).json()

    response = client.get(f"/api/reports/exports/{generated['export_id']}/download/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")


def test_admin_can_list_exports(client):
    admin = _user_with_role("admin_list", "Admin")
    report_date = _seed_report_data()
    client.force_login(admin)

    client.post(
        "/api/reports/exports/generate/",
        data=json.dumps({"format": "PDF", "filters": {"date": str(report_date)}}),
        content_type="application/json",
    )

    response = client.get("/api/reports/exports/list/")

    assert response.status_code == 200
    assert response.json()["count"] >= 1
