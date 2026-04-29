"""Integration tests — Epic 4: Billing handoff endpoints (Stories 4.1, 4.2, 4.3)."""
import datetime

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient
from apps.core.services import (
    create_billing_handoff,
    create_or_update_consultation_draft,
    finalize_consultation,
    send_billing_handoff,
)
import apps.core.services as svc


pytestmark = pytest.mark.django_db


def _user_with_role(username, role):
    user = User.objects.create_user(username=username, password="pass1234")
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


def _seed_finalized(suffix=""):
    patient = Patient.objects.create(
        first_name="BillEp", last_name=f"Int{suffix}",
        dob=datetime.date(1978, 9, 10), gender="F", phone=f"92000000{suffix}01",
    )
    doctor = Doctor.objects.create(full_name=f"Dr.BillInt{suffix}", specialty="Cardiology")
    slot_date = datetime.date(2026, 7, 1)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(11, 0), end_time=datetime.time(11, 10))
    appt = Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(11, 0), end_time=datetime.time(11, 10),
        visit_type="FOLLOW_UP", channel="WALK_IN", status="BOOKED",
    )
    c = create_or_update_consultation_draft(appt.id, {"diagnosis": "Atrial Fibrillation"}, "dr_card")
    return finalize_consultation(c.id, "dr_card")


# ---- Story 4.1: Create handoff ----

def test_doctor_creates_billing_handoff(client):
    user = _user_with_role("dr_bill_ep1", "Doctor")
    client.force_login(user)
    c = _seed_finalized("1")

    response = client.post(f"/api/consultations/{c.id}/billing/handoff/")

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert data["consultation_id"] == c.id
    assert data["patient_mrn"].startswith("MRN-")


def test_duplicate_handoff_returns_400(client):
    user = _user_with_role("dr_bill_ep2", "Doctor")
    client.force_login(user)
    c = _seed_finalized("2")

    client.post(f"/api/consultations/{c.id}/billing/handoff/")
    response = client.post(f"/api/consultations/{c.id}/billing/handoff/")
    assert response.status_code == 400
    assert "billing_handoff_already_exists" in response.json()["error"]


def test_receptionist_cannot_create_billing_handoff(client):
    user = _user_with_role("recv_bill", "Receptionist")
    client.force_login(user)
    c = _seed_finalized("3")

    response = client.post(f"/api/consultations/{c.id}/billing/handoff/")
    assert response.status_code == 403


# ---- Story 4.2: Send handoff + retry ----

def test_admin_sends_billing_handoff_success(client):
    admin = _user_with_role("admin_send1", "Admin")
    client.force_login(admin)
    c = _seed_finalized("4")
    handoff = create_billing_handoff(c.id, "admin_send1")

    response = client.post(f"/api/billing/handoffs/{handoff.id}/send/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["retry_count"] == 1


def test_admin_send_failed_handoff_sets_next_retry(client, monkeypatch):
    def _fail(payload):
        raise RuntimeError("gateway_timeout")

    monkeypatch.setattr(svc, "_billing_adapter", _fail)

    admin = _user_with_role("admin_send2", "Admin")
    client.force_login(admin)
    c = _seed_finalized("5")
    handoff = create_billing_handoff(c.id, "admin_send2")

    response = client.post(f"/api/billing/handoffs/{handoff.id}/send/")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "FAILED"
    assert data["next_retry_at"] is not None


def test_non_admin_cannot_send_handoff(client):
    dr = _user_with_role("dr_send_nope", "Doctor")
    client.force_login(dr)
    c = _seed_finalized("6")
    handoff = create_billing_handoff(c.id, "dr_send_nope")

    response = client.post(f"/api/billing/handoffs/{handoff.id}/send/")
    assert response.status_code == 403


# ---- Story 4.3: Reconciliation ----

def test_admin_reconcile_returns_all_handoffs(client):
    admin = _user_with_role("admin_recon1", "Admin")
    c1 = _seed_finalized("7")
    c2 = _seed_finalized("8")
    create_billing_handoff(c1.id, "admin_recon1")
    create_billing_handoff(c2.id, "admin_recon1")

    client.force_login(admin)
    response = client.get("/api/billing/reconcile/")
    assert response.status_code == 200
    assert response.json()["count"] >= 2


def test_reconcile_filter_by_status(client):
    admin = _user_with_role("admin_recon2", "Admin")
    c1 = _seed_finalized("9")
    c2 = _seed_finalized("10")
    h1 = create_billing_handoff(c1.id, "admin_recon2")
    create_billing_handoff(c2.id, "admin_recon2")
    send_billing_handoff(h1.id)  # marks SUCCESS

    client.force_login(admin)
    response = client.get("/api/billing/reconcile/?status=SUCCESS")
    assert response.status_code == 200
    data = response.json()
    ids = [r["handoff_id"] for r in data["results"]]
    assert h1.id in ids
    pending_ids = [r["handoff_id"] for r in data["results"] if r["status"] == "PENDING"]
    assert len(pending_ids) == 0


def test_non_admin_cannot_access_reconcile(client):
    dr = _user_with_role("dr_recon_nope", "Doctor")
    client.force_login(dr)
    response = client.get("/api/billing/reconcile/")
    assert response.status_code == 403
