import datetime
import json

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Appointment, Doctor, DoctorSlot, Patient
from apps.core.services import create_or_update_consultation_draft, finalize_consultation


pytestmark = pytest.mark.django_db


def _user_with_role(username, role):
    user = User.objects.create_user(username=username, password="pass1234")
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


def _seed_finalized(suffix=""):
    patient = Patient.objects.create(
        first_name="Nisha", last_name=f"Ep{suffix}",
        dob=datetime.date(1992, 6, 1), gender="F", phone=f"990000000{suffix}1",
    )
    doctor = Doctor.objects.create(full_name=f"Dr.Ep{suffix}", specialty="General Medicine")
    slot_date = datetime.date(2026, 5, 20)
    DoctorSlot.objects.create(doctor=doctor, slot_date=slot_date, start_time=datetime.time(9, 0), end_time=datetime.time(9, 10))
    appt = Appointment.objects.create(
        patient=patient, doctor=doctor, slot_date=slot_date,
        start_time=datetime.time(9, 0), end_time=datetime.time(9, 10),
        visit_type="NEW", channel="WALK_IN", status="BOOKED",
    )
    c = create_or_update_consultation_draft(appt.id, {"diagnosis": "Anaemia"}, "dr_ep")
    return finalize_consultation(c.id, "dr_ep")


VALID_PAYLOAD = {
    "items": [
        {
            "drug": "Ferrous Sulphate",
            "dosage_form": "Tablet",
            "strength": "200mg",
            "dose": "1 tablet",
            "frequency": "BD",
            "duration": "60 days",
            "timing": "after_food",
            "route": "oral",
            "instructions": "Take after meals with water. Avoid tea/coffee within 1 hour.",
        }
    ],
    "doctor_qualification": "MBBS, MD (Medicine)",
    "doctor_reg_number": "MH-98765",
    "clinic_name": "City OPD Clinic",
    "clinic_address": "123, MG Road, Pune, Maharashtra - 411001",
    "special_instructions": "Avoid self-medication. Follow up after 4 weeks.",
    "validity_days": 30,
}


def test_doctor_issues_indian_prescription(client):
    user = _user_with_role("dr_rx_ep", "Doctor")
    client.force_login(user)
    consultation = _seed_finalized("1")

    response = client.post(
        f"/api/consultations/{consultation.id}/prescription/",
        data=json.dumps(VALID_PAYLOAD),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["items"][0]["drug"] == "Ferrous Sulphate"
    assert data["items"][0]["frequency"] == "BD"
    assert "rx_number" in data
    assert data["rx_number"].startswith("RX-")


def test_pharmacist_gets_indian_format_prescription(client):
    dr = _user_with_role("dr_issue2", "Doctor")
    consultation = _seed_finalized("2")
    client.force_login(dr)
    client.post(
        f"/api/consultations/{consultation.id}/prescription/",
        data=json.dumps(VALID_PAYLOAD),
        content_type="application/json",
    )

    pharm = _user_with_role("pharm_rx", "Pharmacist")
    client.force_login(pharm)
    response = client.get(f"/api/consultations/{consultation.id}/prescription/get/")

    assert response.status_code == 200
    data = response.json()
    # Indian header checks
    assert "rx_number" in data
    assert data["doctor"]["specialty"] == "General Medicine"
    assert data["doctor"]["qualification"] == "MBBS, MD (Medicine)"
    assert data["doctor"]["reg_number"] == "MH-98765"
    assert data["clinic"]["name"] == "City OPD Clinic"
    # Patient section
    assert data["patient"]["sex"] == "Female"
    assert data["patient"]["age"] is not None
    assert "mrn" not in data["patient"]
    # Rx items
    assert data["items"][0]["sno"] == 1
    assert data["items"][0]["timing"] == "after_food"
    assert data["items"][0]["route"] == "oral"
    # Footer
    assert "disclaimer" in data


def test_doctor_creates_lab_order(client):
    user = _user_with_role("dr_order_ep", "Doctor")
    client.force_login(user)
    consultation = _seed_finalized("3")

    response = client.post(
        f"/api/consultations/{consultation.id}/orders/",
        {"order_type": "LAB", "description": "HbA1c, CBC"},
    )

    assert response.status_code == 201
    assert response.json()["order_type"] == "LAB"


def test_order_list_returns_all_orders(client):
    user = _user_with_role("dr_order_list", "Doctor")
    client.force_login(user)
    consultation = _seed_finalized("4")

    client.post(f"/api/consultations/{consultation.id}/orders/", {"order_type": "LAB", "description": "CBC"})
    client.post(f"/api/consultations/{consultation.id}/orders/", {"order_type": "RADIOLOGY", "description": "Chest X-Ray PA"})

    response = client.get(f"/api/consultations/{consultation.id}/orders/list/")
    assert response.status_code == 200
    assert len(response.json()["orders"]) == 2


def test_receptionist_cannot_issue_prescription(client):
    user = _user_with_role("recv_rx", "Receptionist")
    client.force_login(user)
    consultation = _seed_finalized("5")

    response = client.post(
        f"/api/consultations/{consultation.id}/prescription/",
        data=json.dumps(VALID_PAYLOAD),
        content_type="application/json",
    )
    assert response.status_code == 403
