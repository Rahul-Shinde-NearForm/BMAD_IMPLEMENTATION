import datetime

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Appointment, AppointmentEvent, Doctor, DoctorSlot, Patient


pytestmark = pytest.mark.django_db


def _seed_patient_and_doctor_with_slot():
    patient = Patient.objects.create(
        first_name="Ravi",
        last_name="Kulkarni",
        dob=datetime.date(1993, 7, 21),
        gender="M",
        phone="9000000001",
    )
    doctor = Doctor.objects.create(full_name="Dr. Rao", specialty="General Medicine")
    DoctorSlot.objects.create(
        doctor=doctor,
        slot_date=datetime.date(2026, 5, 4),
        start_time=datetime.time(9, 0),
        end_time=datetime.time(9, 10),
    )
    DoctorSlot.objects.create(
        doctor=doctor,
        slot_date=datetime.date(2026, 5, 4),
        start_time=datetime.time(9, 10),
        end_time=datetime.time(9, 20),
    )
    return patient, doctor


def test_appointment_book_reschedule_cancel_flow(client):
    user = User.objects.create_user(username="reception_flow", password="pass1234")
    group, _ = Group.objects.get_or_create(name="Receptionist")
    user.groups.add(group)
    client.force_login(user)
    patient, doctor = _seed_patient_and_doctor_with_slot()

    book_response = client.post(
        "/api/appointments/book/",
        {
            "patient_id": patient.id,
            "doctor_id": doctor.id,
            "slot_date": "2026-05-04",
            "start_time": "09:00",
            "end_time": "09:10",
            "visit_type": "NEW",
            "channel": "WALK_IN",
        },
    )
    assert book_response.status_code == 201
    appointment_id = book_response.json()["appointment_id"]

    reschedule_response = client.post(
        f"/api/appointments/{appointment_id}/reschedule/",
        {
            "slot_date": "2026-05-04",
            "start_time": "09:10",
            "end_time": "09:20",
            "reason": "Doctor delayed",
        },
    )
    assert reschedule_response.status_code == 200
    assert reschedule_response.json()["status"] == "RESCHEDULED"

    cancel_response = client.post(
        f"/api/appointments/{appointment_id}/cancel/",
        {"reason": "Patient unavailable"},
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"

    appointment = Appointment.objects.get(id=appointment_id)
    assert appointment.status == "CANCELLED"
    assert appointment.events.count() == 3


def test_appointment_booking_blocks_after_overbooking_limit(client):
    user = User.objects.create_user(username="reception_overbook", password="pass1234")
    group, _ = Group.objects.get_or_create(name="Receptionist")
    user.groups.add(group)
    client.force_login(user)
    patient, doctor = _seed_patient_and_doctor_with_slot()

    for i in range(4):
        p = Patient.objects.create(
            first_name=f"P{i}",
            last_name="Test",
            dob=datetime.date(1990, 1, 1),
            gender="M",
            phone=f"910000000{i}",
        )
        response = client.post(
            "/api/appointments/book/",
            {
                "patient_id": p.id,
                "doctor_id": doctor.id,
                "slot_date": "2026-05-04",
                "start_time": "09:00",
                "end_time": "09:10",
                "visit_type": "NEW",
                "channel": "WALK_IN",
            },
        )
        assert response.status_code == 201

    blocked = client.post(
        "/api/appointments/book/",
        {
            "patient_id": patient.id,
            "doctor_id": doctor.id,
            "slot_date": "2026-05-04",
            "start_time": "09:00",
            "end_time": "09:10",
            "visit_type": "NEW",
            "channel": "WALK_IN",
        },
    )

    assert blocked.status_code == 409
    assert blocked.json()["error"] == "overbooking_limit_reached"
