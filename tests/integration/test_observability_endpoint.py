import json

import pytest
from django.contrib.auth.models import Group, User


pytestmark = pytest.mark.django_db


def _user_with_role(username, role):
    user = User.objects.create_user(username=username, password="pass1234")
    group, _ = Group.objects.get_or_create(name=role)
    user.groups.add(group)
    return user


def test_admin_can_view_observability_snapshot(client):
    admin = _user_with_role("admin_obs", "Admin")
    client.force_login(admin)

    response = client.get("/api/observability/snapshot/?queue_lag_threshold=10&billing_backlog_threshold=5")

    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert "alerts" in data


def test_non_admin_cannot_view_observability_snapshot(client):
    doctor = _user_with_role("doc_obs", "Doctor")
    client.force_login(doctor)

    response = client.get("/api/observability/snapshot/")
    assert response.status_code == 403


def test_admin_can_create_and_resolve_incident(client):
    admin = _user_with_role("admin_inc", "Admin")
    client.force_login(admin)

    create_resp = client.post(
        "/api/incidents/create/",
        data=json.dumps(
            {
                "severity": "WARN",
                "source": "manual",
                "summary": "Queue monitor alert",
                "runbook_ref": "runbooks/opd-incident-response.md",
                "details": {"queue_lag": 44},
            }
        ),
        content_type="application/json",
    )
    assert create_resp.status_code == 201
    incident_id = create_resp.json()["incident_id"]

    resolve_resp = client.post(f"/api/incidents/{incident_id}/resolve/")
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "RESOLVED"


def test_admin_can_list_incidents(client):
    admin = _user_with_role("admin_inc_list", "Admin")
    client.force_login(admin)

    client.post(
        "/api/incidents/create/",
        data=json.dumps({"severity": "WARN", "source": "manual", "summary": "List me", "details": {}}),
        content_type="application/json",
    )

    response = client.get("/api/incidents/list/")
    assert response.status_code == 200
    assert response.json()["count"] >= 1
