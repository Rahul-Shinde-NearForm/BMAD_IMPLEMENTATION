import pytest
from django.contrib.auth.models import Group, User


pytestmark = pytest.mark.django_db


def _user_with_role(username, role):
    user = User.objects.create_user(username=username, password="pass1234")
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


def test_home_shows_doctor_workbench_link_for_doctor(client):
    user = _user_with_role("doc_home", "Doctor")
    client.force_login(user)

    response = client.get("/")

    assert response.status_code == 200
    assert b"/workbench/doctor/" in response.content


def test_doctor_can_open_doctor_workbench(client):
    user = _user_with_role("doc_open", "Doctor")
    client.force_login(user)

    response = client.get("/workbench/doctor/")

    assert response.status_code == 200
    assert b"Doctor Workbench" in response.content


def test_doctor_cannot_open_reception_workbench(client):
    user = _user_with_role("doc_blocked", "Doctor")
    client.force_login(user)

    response = client.get("/workbench/reception/")

    assert response.status_code == 403


def test_receptionist_can_open_reception_workbench(client):
    user = _user_with_role("rec_open", "Receptionist")
    client.force_login(user)

    response = client.get("/workbench/reception/")

    assert response.status_code == 200
    assert b"Reception Workbench" in response.content


def test_pharmacist_can_open_pharmacy_workbench(client):
    user = _user_with_role("pharm_open", "Pharmacist")
    client.force_login(user)

    response = client.get("/workbench/pharmacy/")

    assert response.status_code == 200
    assert b"Pharmacy Workbench" in response.content
