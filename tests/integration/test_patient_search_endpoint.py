import datetime

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Patient, SearchAuditLog


pytestmark = pytest.mark.django_db


def test_patient_search_by_mrn_returns_expected_item(client):
    user = User.objects.create_user(username="reception_search", password="pass1234")
    group, _ = Group.objects.get_or_create(name="Receptionist")
    user.groups.add(group)
    client.force_login(user)

    patient = Patient.objects.create(
        first_name="Meera",
        last_name="Joshi",
        dob=datetime.date(1992, 6, 1),
        gender="F",
        phone="7777777777",
    )

    response = client.get(f"/api/patients/search/?mrn={patient.mrn}")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["mrn"] == patient.mrn


def test_patient_search_writes_audit_trail(client):
    user = User.objects.create_user(username="reception_audit", password="pass1234")
    group, _ = Group.objects.get_or_create(name="Receptionist")
    user.groups.add(group)
    client.force_login(user)

    Patient.objects.create(
        first_name="Amit",
        last_name="Patil",
        dob=datetime.date(1989, 4, 11),
        gender="M",
        phone="6666666666",
    )

    response = client.get("/api/patients/search/?phone=6666666666")

    assert response.status_code == 200
    assert SearchAuditLog.objects.filter(actor_username="reception_audit", query_type="phone").exists()
