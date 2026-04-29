from datetime import date, time

from apps.core.services import generate_slots_for_day


def test_generate_slots_for_day_excludes_break_window():
    slots = generate_slots_for_day(
        slot_date=date(2026, 5, 4),
        start_time=time(9, 0),
        end_time=time(10, 0),
        break_start=time(9, 20),
        break_end=time(9, 40),
        slot_minutes=10,
    )

    assert slots == [(time(9, 0), time(9, 10)), (time(9, 10), time(9, 20)), (time(9, 40), time(9, 50)), (time(9, 50), time(10, 0))]
