import pytest
from datetime import datetime, timedelta

from app.utils.ancient_egyptian_calendar import (
    to_ancient_egyptian_date, format_ancient_egyptian_date, EPOCH,
)

pytestmark = pytest.mark.unit


def test_epoch_date_is_day_one_of_thoth_in_akhet():
    result = to_ancient_egyptian_date(EPOCH)

    assert result == {'season': 'Akhet', 'month': 'Thoth', 'day': 1, 'is_epagomenal': False}


def test_day_after_epoch_is_day_two_of_thoth():
    result = to_ancient_egyptian_date(EPOCH + timedelta(days=1))

    assert result == {'season': 'Akhet', 'month': 'Thoth', 'day': 2, 'is_epagomenal': False}


def test_thirtieth_day_rolls_over_to_second_month():
    """Day 30 of the cycle (0-indexed) is the 1st of the 2nd month, not a
    31st day of the 1st -- each month is exactly 30 days."""
    result = to_ancient_egyptian_date(EPOCH + timedelta(days=30))

    assert result == {'season': 'Akhet', 'month': 'Phaophi', 'day': 1, 'is_epagomenal': False}


def test_accepts_datetime_as_well_as_date():
    as_date = to_ancient_egyptian_date(EPOCH)
    as_datetime = to_ancient_egyptian_date(datetime(EPOCH.year, EPOCH.month, EPOCH.day, 15, 30))

    assert as_date == as_datetime


def test_season_boundaries_align_with_month_groups():
    # Month index 3 (Choiak, 0-indexed) is the last month of Akhet.
    choiak_first_day = to_ancient_egyptian_date(EPOCH + timedelta(days=30 * 3))
    assert choiak_first_day['season'] == 'Akhet'
    assert choiak_first_day['month'] == 'Choiak'

    # Month index 4 (Tybi) is the first month of Peret.
    tybi_first_day = to_ancient_egyptian_date(EPOCH + timedelta(days=30 * 4))
    assert tybi_first_day['season'] == 'Peret'
    assert tybi_first_day['month'] == 'Tybi'

    # Month index 8 (Pachons) is the first month of Shemu.
    pachons_first_day = to_ancient_egyptian_date(EPOCH + timedelta(days=30 * 8))
    assert pachons_first_day['season'] == 'Shemu'
    assert pachons_first_day['month'] == 'Pachons'


def test_epagomenal_days_belong_to_no_month_or_season():
    """Days 361-365 of the 365-day cycle (the 5 epagomenal days, at
    0-indexed cycle positions 360-364) don't belong to any of the 12 named
    months -- the edge case the spec calls out explicitly."""
    first_epagomenal_day = to_ancient_egyptian_date(EPOCH + timedelta(days=360))
    last_epagomenal_day = to_ancient_egyptian_date(EPOCH + timedelta(days=364))

    assert first_epagomenal_day == {'season': None, 'month': None, 'day': 1, 'is_epagomenal': True}
    assert last_epagomenal_day == {'season': None, 'month': None, 'day': 5, 'is_epagomenal': True}


def test_cycle_wraps_back_to_day_one_after_365_days():
    wrapped = to_ancient_egyptian_date(EPOCH + timedelta(days=365))

    assert wrapped == {'season': 'Akhet', 'month': 'Thoth', 'day': 1, 'is_epagomenal': False}


def test_dates_before_the_epoch_wrap_correctly():
    """The modulo arithmetic must handle dates before EPOCH correctly (a
    negative day-difference) rather than raising or returning a negative
    day-in-cycle."""
    the_day_before_epoch = to_ancient_egyptian_date(EPOCH - timedelta(days=1))

    # One day before "1 Thoth" is the last epagomenal day of the previous cycle.
    assert the_day_before_epoch == {'season': None, 'month': None, 'day': 5, 'is_epagomenal': True}


def test_format_ancient_egyptian_date_for_a_regular_day():
    converted = {'season': 'Shemu', 'month': 'Mesore', 'day': 12, 'is_epagomenal': False}
    assert format_ancient_egyptian_date(converted) == "12 Mesore (Shemu)"


def test_format_ancient_egyptian_date_for_an_epagomenal_day():
    converted = {'season': None, 'month': None, 'day': 3, 'is_epagomenal': True}
    assert format_ancient_egyptian_date(converted) == "Epagomenal day 3"
