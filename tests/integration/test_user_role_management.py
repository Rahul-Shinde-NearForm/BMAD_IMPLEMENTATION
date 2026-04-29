import pytest
from django.contrib.auth.models import Group, User


pytestmark = pytest.mark.django_db


def test_user_role_management_requires_admin_role(client):
    user = User.objects.create_user(username="doctor_user", password="pass1234")
    doctor_group, _ = Group.objects.get_or_create(name="Doctor")
    user.groups.add(doctor_group)
    client.force_login(user)

    response = client.get("/users/manage/")

    assert response.status_code == 403


def test_admin_can_open_management_page(client):
    user = User.objects.create_user(username="admin_staff", password="pass1234")
    admin_group, _ = Group.objects.get_or_create(name="Admin")
    user.groups.add(admin_group)
    client.force_login(user)

    response = client.get("/users/manage/")

    assert response.status_code == 200
    assert b"User and Role Management" in response.content


def test_admin_can_create_user_with_role(client):
    user = User.objects.create_user(username="admin_create", password="pass1234")
    admin_group, _ = Group.objects.get_or_create(name="Admin")
    user.groups.add(admin_group)
    client.force_login(user)

    response = client.post(
        "/api/users/create/",
        {"username": "reception_new", "password": "pass1234", "role": "Receptionist"},
    )

    assert response.status_code == 302
    assert "/users/manage/?status=success" in response["Location"]
    created = User.objects.get(username="reception_new")
    assert created.groups.filter(name="Receptionist").exists()


def test_admin_can_reassign_user_role(client):
    admin = User.objects.create_user(username="admin_assign", password="pass1234")
    admin_group, _ = Group.objects.get_or_create(name="Admin")
    admin.groups.add(admin_group)

    target = User.objects.create_user(username="target_user", password="pass1234")
    receptionist_group, _ = Group.objects.get_or_create(name="Receptionist")
    target.groups.add(receptionist_group)

    client.force_login(admin)
    response = client.post(
        "/api/users/assign-role/",
        {"user_id": target.id, "role": "Pharmacist"},
    )

    assert response.status_code == 302
    assert "/users/manage/?status=success" in response["Location"]
    target.refresh_from_db()
    assert target.groups.filter(name="Pharmacist").exists()
    assert not target.groups.filter(name="Receptionist").exists()
