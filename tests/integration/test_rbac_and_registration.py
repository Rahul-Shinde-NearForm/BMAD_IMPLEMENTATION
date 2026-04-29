import datetime

import pytest
from django.contrib.auth.models import Group, User

from apps.core.models import Patient


pytestmark = pytest.mark.django_db


def test_rbac_bootstrap_forbidden_for_non_superuser(client):
    user = User.objects.create_user(username="staff1", password="pass1234")
    client.force_login(user)

    response = client.post("/api/rbac/bootstrap/")

    assert response.status_code == 403


def test_rbac_bootstrap_allows_superuser(client):
    superuser = User.objects.create_superuser(username="admin", email="admin@example.com", password="pass1234")
    client.force_login(superuser)

    response = client.post("/api/rbac/bootstrap/")

    assert response.status_code == 200
    assert "Receptionist" in response.json()["groups"]


def test_patient_register_returns_duplicate_warning(client):
    user = User.objects.create_user(username="reception", password="pass1234")
    group, _ = Group.objects.get_or_create(name="Receptionist")
    user.groups.add(group)
    client.force_login(user)

    Patient.objects.create(
        first_name="Rahul",
        last_name="Shinde",
        dob=datetime.date(1991, 1, 2),
        gender="M",
        phone="9999999999",
        national_id="NID-100",
    )

    response = client.post(
        "/api/patients/register/",
        {
            "first_name": "Rahul",
            "last_name": "Shinde",
            "dob": "1991-01-02",
            "gender": "M",
            "phone": "9999999999",
            "national_id": "NID-100",
        },
    )

    assert response.status_code == 409
    assert response.json()["warning"] == "possible_duplicate"


def test_patient_register_with_confirm_duplicate_creates_record(client):
    user = User.objects.create_user(username="reception2", password="pass1234")
    group, _ = Group.objects.get_or_create(name="Receptionist")
    user.groups.add(group)
    client.force_login(user)

    response = client.post(
        "/api/patients/register/",
        {
            "first_name": "Anita",
            "last_name": "Patil",
            "dob": "1995-10-10",
            "gender": "F",
            "phone": "8888888888",
            "national_id": "NID-999",
            "confirm_duplicate": "true",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "created"
