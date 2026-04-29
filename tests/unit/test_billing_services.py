"""Unit tests — Epic 4: Billing handoff (Stories 4.1, 4.2, 4.3)."""
import datetime

import pytest

from apps.core.models import Appointment, BillingHandoff, BillingRetryLog, Doctor, DoctorSlot, Patient
from apps.core.services import (
    create_billing_handoff,
    list_billing_handoffs,
    send_billing_handoff,
)
from apps.core.services import create_or_update_consultation_draft, finalize_consultation
import apps.core.services as svc


pytestmark = pytest.mark.django_db


def _seed_finalized(suffix=""):
    patient = Patient.objects.create(
        first_name="Billing", last_name=f"Unit{suffix}",
        dob=datetime.date(1985, 3, 15), gender="M", phone=f"91000000{suffix}01",
    )
    doctor = Doctor.objects.create(full_name=f"Dr.BillUnit{suffix}", specialty="Internal Medicine")
    slot_date = datetime.date(2026, 6, 1)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(10, 0), end_time=datetime.time(10, 10))
    appt = Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(10, 0), end_time=datetime.time(10, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )
    c = create_or_update_consultation_draft(appt.id, {"diagnosis": "Hypertension"}, "dr_bill")
    return finalize_consultation(c.id, "dr_bill")


# ---- Story 4.1: Billing handoff creation ----

def test_create_billing_handoff_returns_pending(db):
    c = _seed_finalized("1")
    handoff = create_billing_handoff(c.id, "admin_user")
    assert handoff.status == "PENDING"
    assert handoff.retry_count == 0
    assert handoff.consultation_id == c.id


def test_billing_payload_contains_required_fields(db):
    c = _seed_finalized("2")
    handoff = create_billing_handoff(c.id, "admin_user")
    p = handoff.payload
    assert "consultation_id" in p
    assert "mrn" in p
    assert "patient_name" in p
    assert "diagnosis" in p
    assert "finalized_at" in p


def test_create_billing_handoff_fails_if_not_finalized(db):
    patient = Patient.objects.create(
        first_name="Draft", last_name="Only", dob=datetime.date(1990, 1, 1), gender="M", phone="9000000001",
    )
    doctor = Doctor.objects.create(full_name="Dr.Draft", specialty="General")
    slot_date = datetime.date(2026, 6, 2)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(9, 0), end_time=datetime.time(9, 10))
    appt = Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(9, 0), end_time=datetime.time(9, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )
    c = create_or_update_consultation_draft(appt.id, {"diagnosis": "Check"}, "dr_x")
    with pytest.raises(ValueError, match="consultation_not_finalized"):
        create_billing_handoff(c.id, "admin_user")


def test_create_billing_handoff_rejects_duplicate(db):
    c = _seed_finalized("3")
    create_billing_handoff(c.id, "admin_user")
    with pytest.raises(ValueError, match="billing_handoff_already_exists"):
        create_billing_handoff(c.id, "admin_user")


# ---- Story 4.2: Send + retry + dead-letter ----

def test_send_billing_handoff_success(db):
    c = _seed_finalized("4")
    handoff = create_billing_handoff(c.id, "admin_user")
    result = send_billing_handoff(handoff.id, "admin_user")
    assert result.status == "SUCCESS"
    assert result.retry_count == 1
    log = BillingRetryLog.objects.get(handoff=result)
    assert log.outcome == "SUCCESS"


def test_send_billing_handoff_failure_increments_retry(db, monkeypatch):
    def _fail(payload):
        raise RuntimeError("downstream_unavailable")

    monkeypatch.setattr(svc, "_billing_adapter", _fail)

    c = _seed_finalized("5")
    handoff = create_billing_handoff(c.id, "admin_user")
    result = send_billing_handoff(handoff.id, "admin_user")
    assert result.status == "FAILED"
    assert result.retry_count == 1
    assert result.next_retry_at is not None
    assert "downstream_unavailable" in result.failure_reason


def test_dead_letter_after_max_retries(db, monkeypatch):
    def _fail(payload):
        raise RuntimeError("persistent_failure")

    monkeypatch.setattr(svc, "_billing_adapter", _fail)
    monkeypatch.setattr(svc, "MAX_BILLING_RETRIES", 2)

    c = _seed_finalized("6")
    handoff = create_billing_handoff(c.id, "admin_user")
    send_billing_handoff(handoff.id)  # attempt 1
    handoff.refresh_from_db()
    send_billing_handoff(handoff.id)  # attempt 2 — reaches max
    handoff.refresh_from_db()
    assert handoff.status == "DEAD_LETTER"
    assert handoff.next_retry_at is None


def test_cannot_resend_success(db):
    c = _seed_finalized("7")
    handoff = create_billing_handoff(c.id, "admin_user")
    send_billing_handoff(handoff.id)
    with pytest.raises(ValueError, match="handoff_already_succeeded"):
        send_billing_handoff(handoff.id)


def test_cannot_resend_dead_letter(db, monkeypatch):
    def _fail(payload):
        raise RuntimeError("error")

    monkeypatch.setattr(svc, "_billing_adapter", _fail)
    monkeypatch.setattr(svc, "MAX_BILLING_RETRIES", 1)

    c = _seed_finalized("8")
    handoff = create_billing_handoff(c.id, "admin_user")
    send_billing_handoff(handoff.id)
    handoff.refresh_from_db()
    assert handoff.status == "DEAD_LETTER"
    with pytest.raises(ValueError, match="handoff_is_dead_letter"):
        send_billing_handoff(handoff.id)


# ---- Story 4.3: Reconciliation filter ----

def test_list_billing_handoffs_filters_by_status(db):
    c1 = _seed_finalized("9")
    c2 = _seed_finalized("10")
    h1 = create_billing_handoff(c1.id, "admin_user")
    h2 = create_billing_handoff(c2.id, "admin_user")
    send_billing_handoff(h1.id)  # SUCCESS with default adapter

    results = list_billing_handoffs(status="SUCCESS")
    ids = [h.id for h in results]
    assert h1.id in ids
    assert h2.id not in ids


def test_list_billing_handoffs_no_filter_returns_all(db):
    c1 = _seed_finalized("11")
    c2 = _seed_finalized("12")
    create_billing_handoff(c1.id, "admin_user")
    create_billing_handoff(c2.id, "admin_user")
    results = list_billing_handoffs()
    assert len(results) >= 2
