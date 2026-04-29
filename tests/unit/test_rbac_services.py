import datetime

from django.contrib.auth.models import Group

from apps.core.models import Patient
from apps.core.services import bootstrap_roles, find_duplicate_candidates


def test_bootstrap_roles_creates_expected_groups(db):
    created = bootstrap_roles()

    assert "Receptionist" in created
    assert "Doctor" in created
    assert "Pharmacist" in created
    assert Group.objects.filter(name="Admin").exists()


def test_find_duplicate_candidates_matches_phone_and_identity(db):
    Patient.objects.create(
        first_name="Rahul",
        last_name="Shinde",
        dob=datetime.date(1991, 1, 2),
        gender="M",
        phone="9999999999",
        national_id="NID-1",
    )

    candidates = find_duplicate_candidates(
        {
            "first_name": "Rahul",
            "last_name": "Shinde",
            "dob": datetime.date(1991, 1, 2),
            "gender": "M",
            "phone": "9999999999",
            "national_id": "NID-1",
        }
    )

    assert candidates.count() == 1
