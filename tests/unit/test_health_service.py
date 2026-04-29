from apps.core.services import health_payload


def test_health_payload_has_expected_shape():
    payload = health_payload()

    assert payload["status"] == "ok"
    assert payload["service"] == "opd-management"
