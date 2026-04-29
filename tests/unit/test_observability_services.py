import pytest

from apps.core.models import BillingHandoff, IncidentRecord, QueueItem
from apps.core.services import (
    create_incident_record,
    evaluate_alert_rules,
    observability_snapshot,
    resolve_incident_record,
)


pytestmark = pytest.mark.django_db


def test_evaluate_alert_rules_returns_warn_or_critical():
    alerts = evaluate_alert_rules(queue_lag=30, billing_backlog=25, queue_lag_threshold=20, billing_backlog_threshold=10)
    assert len(alerts) == 2
    severities = {a["severity"] for a in alerts}
    assert "WARN" in severities or "CRITICAL" in severities


def test_observability_snapshot_creates_critical_incident_when_threshold_crossed(monkeypatch):
    monkeypatch.setattr(QueueItem.objects, "filter", lambda **kwargs: type("X", (), {"count": lambda s: 100})())
    monkeypatch.setattr(BillingHandoff.objects, "filter", lambda **kwargs: type("Y", (), {"count": lambda s: 0})())

    snapshot = observability_snapshot(actor_username="admin", queue_lag_threshold=10, billing_backlog_threshold=10)

    assert snapshot["metrics"]["queue_lag"] == 100
    assert IncidentRecord.objects.filter(status="OPEN").count() >= 1


def test_create_and_resolve_incident_flow():
    incident = create_incident_record(
        severity="WARN",
        source="manual",
        summary="Test incident",
        runbook_ref="runbooks/opd.md",
        details={"a": 1},
        actor_username="admin",
    )
    assert incident.status == "OPEN"

    resolved = resolve_incident_record(incident.id, "admin")
    assert resolved.status == "RESOLVED"
    assert resolved.resolved_by == "admin"


def test_invalid_incident_severity_rejected():
    with pytest.raises(ValueError, match="invalid_severity"):
        create_incident_record(
            severity="LOW",
            source="manual",
            summary="Invalid",
            runbook_ref="",
            details={},
            actor_username="admin",
        )
