import datetime

from apps.core.models import Patient
from apps.core.services import log_search, search_patients


def test_search_patients_by_mrn_returns_single_record(db):
    patient = Patient.objects.create(
        first_name="Rahul",
        last_name="Shinde",
        dob=datetime.date(1991, 1, 2),
        gender="M",
        phone="9999999999",
    )

    results = search_patients(mrn=patient.mrn)

    assert results.count() == 1
    assert results.first().id == patient.id


def test_search_patients_by_name_and_dob(db):
    Patient.objects.create(
        first_name="Asha",
        last_name="Kulkarni",
        dob=datetime.date(1990, 5, 10),
        gender="F",
        phone="8888888888",
    )

    results = search_patients(name="Asha Kulkarni", dob="1990-05-10")

    assert results.count() == 1


def test_log_search_persists_audit_entry(db):
    audit = log_search("reception", "mrn", "MRN-000001", 1)

    assert audit.actor_username == "reception"
    assert audit.query_type == "mrn"
    assert audit.result_count == 1
