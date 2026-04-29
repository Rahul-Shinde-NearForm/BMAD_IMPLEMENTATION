import datetime

import pytest

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient, QueueItem
from apps.core.services import call_next, queue_action


pytestmark = pytest.mark.django_db


def _seed_queue_ready_appointment():
    patient = Patient.objects.create(
        first_name="Queue",
        last_name="Patient",
        dob=datetime.date(1992, 1, 1),
        gender="M",
        phone="9200000001",
    )
    doctor = Doctor.objects.create(full_name="Dr. Queue", specialty="General")
    slot_date = datetime.date(2026, 5, 5)
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
    return doctor, slot_date, appointment


def test_call_next_moves_waiting_to_called():
    doctor, slot_date, _ = _seed_queue_ready_appointment()

    queue_item, _, payload = call_next(doctor.id, slot_date, "reception_user")

    assert queue_item.status == "CALLED"
    assert payload["new_status"] == "CALLED"


def test_queue_action_prevents_invalid_recall_transition():
    doctor, slot_date, appointment = _seed_queue_ready_appointment()
    queue_item = QueueItem.objects.create(
        appointment=appointment,
        doctor=doctor,
        slot_date=slot_date,
        token_number=1,
        status="WAITING",
    )

    with pytest.raises(ValueError, match="invalid_transition"):
        queue_action(queue_item.id, "RECALL", "reception_user")


def test_skip_then_recall_is_allowed():
    doctor, slot_date, appointment = _seed_queue_ready_appointment()
    queue_item = QueueItem.objects.create(
        appointment=appointment,
        doctor=doctor,
        slot_date=slot_date,
        token_number=1,
        status="CALLED",
    )

    skipped, _, _ = queue_action(queue_item.id, "SKIP", "reception_user")
    recalled, _, _ = queue_action(skipped.id, "RECALL", "reception_user")

    assert recalled.status == "CALLED"