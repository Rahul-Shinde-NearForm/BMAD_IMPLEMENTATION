import datetime

import pytest

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient, QueueItem
from apps.core.services import daily_kpi_metrics


pytestmark = pytest.mark.django_db


def _seed_day_data():
    doctor = Doctor.objects.create(full_name="Dr KPI", specialty="General Medicine")
    slot_date = datetime.date(2026, 5, 2)

    # Capacity: 4 slots
    for i in range(4):
        start = datetime.time(9, i * 10)
        end = datetime.time(9, i * 10 + 10)
        DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=start, end_time=end)

    p1 = Patient.objects.create(first_name="A", last_name="One", dob=datetime.date(1990, 1, 1), gender="M", phone="9000000001")
    p2 = Patient.objects.create(first_name="B", last_name="Two", dob=datetime.date(1991, 1, 1), gender="F", phone="9000000002")
    p3 = Patient.objects.create(first_name="C", last_name="Three", dob=datetime.date(1992, 1, 1), gender="M", phone="9000000003")

    a1 = Appointment.objects.create(
        patient=p1, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(9, 0), end_time=datetime.time(9, 10),
        visit_type="NEW", channel="WALK_IN", status="COMPLETED",
    )
    a2 = Appointment.objects.create(
        patient=p2, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(9, 10), end_time=datetime.time(9, 20),
        visit_type="FOLLOW_UP", channel="WALK_IN", status="BOOKED",
    )
    a3 = Appointment.objects.create(
        patient=p3, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(9, 20), end_time=datetime.time(9, 30),
        visit_type="NEW", channel="WALK_IN", status="CANCELLED",
    )

    QueueItem.objects.create(appointment=a1, doctor=doctor, slot_date=slot_date, token_number=1, status="CALLED")
    QueueItem.objects.create(appointment=a2, doctor=doctor, slot_date=slot_date, token_number=2, status="NO_SHOW")

    return doctor, slot_date


def test_daily_kpi_metrics_returns_expected_counts():
    doctor, slot_date = _seed_day_data()

    data = daily_kpi_metrics(report_date=slot_date, doctor_id=doctor.id)

    assert data["metrics"]["volume"] == 2  # excludes cancelled
    assert data["metrics"]["completed"] == 1
    assert data["metrics"]["no_show_count"] == 1
    assert data["metrics"]["no_show_rate_pct"] == 50.0
    assert data["metrics"]["utilization_pct"] == 25.0  # 1 completed / 4 slots


def test_daily_kpi_metrics_filters_by_specialty():
    doctor_a = Doctor.objects.create(full_name="Dr A", specialty="Cardiology")
    doctor_b = Doctor.objects.create(full_name="Dr B", specialty="Orthopedics")
    slot_date = datetime.date(2026, 5, 3)

    DoctorSlot.objects.create(doctor=doctor_a, slot_date=slot_date, start_time=datetime.time(10, 0), end_time=datetime.time(10, 10))
    DoctorSlot.objects.create(doctor=doctor_b, slot_date=slot_date, start_time=datetime.time(10, 0), end_time=datetime.time(10, 10))

    pa = Patient.objects.create(first_name="X", last_name="Cardio", dob=datetime.date(1990, 1, 1), gender="M", phone="9000000101")
    pb = Patient.objects.create(first_name="Y", last_name="Ortho", dob=datetime.date(1990, 1, 1), gender="F", phone="9000000102")

    Appointment.objects.create(
        patient=pa, doctor=doctor_a, slot_date=slot_date,
        start_time=datetime.time(10, 0), end_time=datetime.time(10, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )
    Appointment.objects.create(
        patient=pb, doctor=doctor_b, slot_date=slot_date,
        start_time=datetime.time(10, 0), end_time=datetime.time(10, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )

    data = daily_kpi_metrics(report_date=slot_date, specialty="Cardiology")
    assert data["metrics"]["volume"] == 1
