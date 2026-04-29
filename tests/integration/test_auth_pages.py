import pytest
from django.contrib.auth.models import User


pytestmark = pytest.mark.django_db


def test_login_page_renders(client):
    response = client.get("/login/")

    assert response.status_code == 200
    assert b"Login" in response.content


def test_protected_page_redirects_to_login(client):
    response = client.get("/patients/register/")

    assert response.status_code == 302
    assert "/login/" in response["Location"]


def test_login_allows_access_to_protected_page(client):
    user = User.objects.create_user(username="demo_user", password="pass1234")

    login_response = client.post(
        "/login/",
        {"username": user.username, "password": "pass1234"},
    )

    assert login_response.status_code == 302
    assert login_response["Location"] == "/"

    protected = client.get("/patients/register/")
    assert protected.status_code == 200
