import datetime

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient


pytestmark = pytest.mark.django_db


def _seed_user_with_role(role_name):
    user = User.objects.create_user(username=f"{role_name.lower()}_queue", password="pass1234")
    group, _ = Group.objects.get_or_create(name=role_name)
    user.groups.add(group)
    return user


def _seed_appointment():
    patient = Patient.objects.create(
        first_name="Maya",
        last_name="Queue",
        dob=datetime.date(1994, 3, 1),
        gender="F",
        phone="9300000001",
    )
    doctor = Doctor.objects.create(full_name="Dr. Flow", specialty="General")
    slot_date = datetime.date(2026, 5, 6)
    DoctorSlot.objects.create(
        doctor=doctor,
        slot_date=slot_date,
        start_time=datetime.time(11, 0),
        end_time=datetime.time(11, 10),
    )
    appointment = Appointment.objects.create(
        patient=patient,
        doctor=doctor,
        slot_date=slot_date,
        start_time=datetime.time(11, 0),
        end_time=datetime.time(11, 10),
        visit_type="NEW",
        channel="WALK_IN",
        status="BOOKED",
    )
    return doctor, slot_date, appointment


def test_queue_board_returns_waiting_items(client):
    user = _seed_user_with_role("Receptionist")
    client.force_login(user)
    doctor, slot_date, _ = _seed_appointment()

    response = client.get(f"/api/queue/board/?doctor_id={doctor.id}&slot_date={slot_date}")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "WAITING"


def test_queue_call_next_skip_recall_no_show_flow(client):
    user = _seed_user_with_role("Receptionist")
    client.force_login(user)
    doctor, slot_date, _ = _seed_appointment()

    called = client.post("/api/queue/call-next/", {"doctor_id": doctor.id, "slot_date": str(slot_date)})
    assert called.status_code == 200
    queue_item_id = called.json()["queue_item_id"]
    assert called.json()["event"]["action"] == "CALL_NEXT"

    skipped = client.post(f"/api/queue/{queue_item_id}/skip/")
    assert skipped.status_code == 200
    assert skipped.json()["status"] == "SKIPPED"

    recalled = client.post(f"/api/queue/{queue_item_id}/recall/")
    assert recalled.status_code == 200
    assert recalled.json()["status"] == "CALLED"

    no_show = client.post(f"/api/queue/{queue_item_id}/no-show/")
    assert no_show.status_code == 200
    assert no_show.json()["status"] == "NO_SHOW"


def test_queue_call_next_forbidden_for_doctor_role(client):
    user = _seed_user_with_role("Doctor")
    client.force_login(user)
    doctor, slot_date, _ = _seed_appointment()

    response = client.post("/api/queue/call-next/", {"doctor_id": doctor.id, "slot_date": str(slot_date)})

    assert response.status_code == 403