import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import DoctorScheduleTemplate, DoctorSlot


pytestmark = pytest.mark.django_db


def test_schedule_upsert_rejects_non_staff(client):
    user = User.objects.create_user(username="reception_user", password="pass1234")
    client.force_login(user)

    response = client.post(
        "/api/doctors/schedule/upsert/",
        {
            "doctor_name": "Dr. Mehta",
            "specialty": "General Medicine",
            "day_of_week": 0,
            "start_time": "09:00",
            "end_time": "11:00",
            "slot_minutes": 10,
            "range_start": "2026-05-04",
            "range_end": "2026-05-04",
            "reason": "Initial schedule",
        },
    )

    assert response.status_code == 403


def test_schedule_upsert_generates_slots_and_versions(client):
    staff = User.objects.create_user(username="scheduler", password="pass1234", is_staff=True)
    group, _ = Group.objects.get_or_create(name="Admin")
    staff.groups.add(group)
    client.force_login(staff)

    payload = {
        "doctor_name": "Dr. Mehta",
        "specialty": "General Medicine",
        "day_of_week": 0,
        "start_time": "09:00",
        "end_time": "10:00",
        "break_start": "09:20",
        "break_end": "09:40",
        "slot_minutes": 10,
        "range_start": "2026-05-04",
        "range_end": "2026-05-04",
        "reason": "Initial template",
    }

    first = client.post("/api/doctors/schedule/upsert/", payload)
    assert first.status_code == 200
    assert first.json()["schedule_version"] == 1
    assert first.json()["generated_slots"] == 4

    payload["reason"] = "Update with same window"
    second = client.post("/api/doctors/schedule/upsert/", payload)
    assert second.status_code == 200
    assert second.json()["schedule_version"] == 2

    template = DoctorScheduleTemplate.objects.get(doctor__full_name="Dr. Mehta", day_of_week=0)
    assert template.change_reason == "Update with same window"
    assert DoctorSlot.objects.filter(doctor=template.doctor, slot_date="2026-05-04").count() == 4
