from apps.core.services import is_transition_allowed


def test_appointment_transitions_are_enforced():
    assert is_transition_allowed("BOOKED", "RESCHEDULED") is True
    assert is_transition_allowed("BOOKED", "CANCELLED") is True
    assert is_transition_allowed("CANCELLED", "RESCHEDULED") is False
