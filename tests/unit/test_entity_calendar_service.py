import pytest
from datetime import datetime

from app.services.entity_calendar_service import (
    validate_entry_input, _to_expansion_entry, EntityCalendarValidationError,
)
from app.services.custom_calendar_service import expand_entries_for_year

pytestmark = pytest.mark.unit


def test_validate_entry_input_accepts_valid_once_entry(app):
    with app.app_context():
        entry = validate_entry_input({
            'title': 'Closed for renovation',
            'entry_type': 'closure',
            'recurrence': 'once',
            'date': '2026-08-01',
            'description': 'Back Sept 1st',
        })

        assert entry['title'] == 'Closed for renovation'
        assert entry['entry_type'] == 'closure'
        assert entry['recurrence'] == 'once'
        assert entry['date'] == '2026-08-01'
        assert entry['description'] == 'Back Sept 1st'
        assert entry['month'] is None
        assert entry['day'] is None


def test_validate_entry_input_accepts_valid_annual_entry(app):
    with app.app_context():
        entry = validate_entry_input({
            'title': 'Closed for Christmas',
            'entry_type': 'closure',
            'recurrence': 'annual',
            'month': 12,
            'day': 25,
        })

        assert entry['recurrence'] == 'annual'
        assert entry['month'] == 12
        assert entry['day'] == 25
        assert entry['date'] is None


def test_validate_entry_input_defaults_entry_type_to_other(app):
    with app.app_context():
        entry = validate_entry_input({'title': 'Something', 'recurrence': 'once', 'date': '2026-01-01'})
        assert entry['entry_type'] == 'other'


def test_validate_entry_input_rejects_missing_title(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="title"):
            validate_entry_input({'recurrence': 'once', 'date': '2026-01-01'})


def test_validate_entry_input_rejects_invalid_entry_type(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="entry_type"):
            validate_entry_input({'title': 'X', 'entry_type': 'not-a-type', 'recurrence': 'once', 'date': '2026-01-01'})


def test_validate_entry_input_rejects_invalid_recurrence(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="recurrence"):
            validate_entry_input({'title': 'X', 'recurrence': 'weekly'})


def test_validate_entry_input_rejects_malformed_once_date(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="date"):
            validate_entry_input({'title': 'X', 'recurrence': 'once', 'date': 'not-a-date'})


def test_validate_entry_input_rejects_out_of_range_month(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="month"):
            validate_entry_input({'title': 'X', 'recurrence': 'annual', 'month': 13, 'day': 1})


def test_validate_entry_input_rejects_invalid_day_for_month(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="day"):
            validate_entry_input({'title': 'X', 'recurrence': 'annual', 'month': 4, 'day': 31})


def test_validate_entry_input_allows_feb_29_annual(app):
    with app.app_context():
        entry = validate_entry_input({'title': 'Leap Day', 'recurrence': 'annual', 'month': 2, 'day': 29})
        assert entry['day'] == 29


def test_validate_entry_input_rejects_boolean_month(app):
    """YAML/JSON 'true' for month is an int subclass in Python -- must not be
    silently treated as month 1."""
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="month"):
            validate_entry_input({'title': 'X', 'recurrence': 'annual', 'month': True, 'day': 1})


def test_validate_entry_input_time_defaults_to_none_when_omitted(app):
    with app.app_context():
        entry = validate_entry_input({'title': 'X', 'recurrence': 'once', 'date': '2026-01-01'})
        assert entry['time'] is None


def test_validate_entry_input_accepts_valid_time(app):
    with app.app_context():
        entry = validate_entry_input({
            'title': 'X', 'recurrence': 'once', 'date': '2026-01-01', 'time': '09:30',
        })
        assert entry['time'] == '09:30'


def test_validate_entry_input_rejects_malformed_time(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="'time'"):
            validate_entry_input({'title': 'X', 'recurrence': 'once', 'date': '2026-01-01', 'time': 'not-a-time'})


def test_validate_entry_input_end_time_defaults_to_none_when_omitted(app):
    with app.app_context():
        entry = validate_entry_input({'title': 'X', 'recurrence': 'once', 'date': '2026-01-01'})
        assert entry['end_time'] is None


def test_validate_entry_input_accepts_valid_end_time(app):
    with app.app_context():
        entry = validate_entry_input({
            'title': 'X', 'recurrence': 'once', 'date': '2026-01-01', 'end_time': '17:00',
        })
        assert entry['end_time'] == '17:00'


def test_validate_entry_input_rejects_malformed_end_time(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="end_time"):
            validate_entry_input({
                'title': 'X', 'recurrence': 'once', 'date': '2026-01-01', 'end_time': 'not-a-time',
            })


def test_validate_entry_input_end_date_defaults_to_none_when_omitted(app):
    with app.app_context():
        entry = validate_entry_input({'title': 'X', 'recurrence': 'once', 'date': '2026-01-01'})
        assert entry['end_date'] is None


def test_validate_entry_input_accepts_valid_end_date(app):
    with app.app_context():
        entry = validate_entry_input({
            'title': 'X', 'recurrence': 'once', 'date': '2026-01-01', 'end_date': '2026-01-03',
        })
        assert entry['end_date'] == '2026-01-03'


def test_validate_entry_input_rejects_malformed_end_date(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="end_date"):
            validate_entry_input({
                'title': 'X', 'recurrence': 'once', 'date': '2026-01-01', 'end_date': 'not-a-date',
            })


# --- nth_weekday / periodic_years / seasonal: dispatch wiring ---
# Field-level validation (bad ordinal/weekday/interval_years/etc.) is
# already covered against the shared validators in
# test_custom_calendar_service.py -- these just confirm the dispatch here
# calls into them correctly for entity entries too.

def test_validate_entry_input_accepts_valid_nth_weekday_entry(app):
    with app.app_context():
        entry = validate_entry_input({
            'title': 'Kentucky Derby', 'recurrence': 'nth_weekday', 'month': 5, 'weekday': 5, 'ordinal': 1,
        })
        assert entry['recurrence'] == 'nth_weekday'
        assert entry['month'] == 5
        assert entry['weekday'] == 5
        assert entry['ordinal'] == 1
        assert entry['day'] is None


def test_validate_entry_input_rejects_invalid_nth_weekday_ordinal(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="ordinal"):
            validate_entry_input({'title': 'X', 'recurrence': 'nth_weekday', 'month': 5, 'weekday': 5, 'ordinal': 0})


def test_validate_entry_input_accepts_valid_periodic_years_entry(app):
    with app.app_context():
        entry = validate_entry_input({
            'title': 'Olympics', 'recurrence': 'periodic_years',
            'interval_years': 4, 'anchor_year': 2024, 'month': 7, 'day': 26,
        })
        assert entry['recurrence'] == 'periodic_years'
        assert entry['interval_years'] == 4
        assert entry['anchor_year'] == 2024


def test_validate_entry_input_rejects_periodic_years_missing_interval(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="interval_years"):
            validate_entry_input({
                'title': 'X', 'recurrence': 'periodic_years', 'anchor_year': 2024, 'month': 7, 'day': 26,
            })


def test_validate_entry_input_accepts_valid_seasonal_entry(app):
    with app.app_context():
        entry = validate_entry_input({'title': 'Some Festival', 'recurrence': 'seasonal', 'month': 10})
        assert entry['recurrence'] == 'seasonal'
        assert entry['month'] == 10
        assert entry['day'] == 1  # defaulted


def test_validate_entry_input_rejects_seasonal_missing_month(app):
    with app.app_context():
        with pytest.raises(EntityCalendarValidationError, match="month"):
            validate_entry_input({'title': 'X', 'recurrence': 'seasonal'})


# --- _to_expansion_entry ---

def test_to_expansion_entry_preserves_actual_recurrence_kind():
    """Regression test: _to_expansion_entry used to hardcode
    'recurrence': 'annual' for every non-'once' entry, which happened to
    be harmless while 'annual' was the only other kind but would have
    silently mis-expanded any nth_weekday/periodic_years/seasonal entry
    stored on an entity as if it were a plain annual one."""
    stored = {
        'title': 'Kentucky Derby', 'recurrence': 'nth_weekday',
        'month': 5, 'day': None, 'weekday': 5, 'ordinal': 1,
        'interval_years': None, 'anchor_year': None, 'description': None,
    }
    expansion_entry = _to_expansion_entry(stored)
    assert expansion_entry['recurrence'] == 'nth_weekday'
    assert expansion_entry['weekday'] == 5
    assert expansion_entry['ordinal'] == 1


def test_to_expansion_entry_still_handles_annual():
    stored = {
        'title': 'Closed for Christmas', 'recurrence': 'annual',
        'month': 12, 'day': 25, 'description': None,
    }
    expansion_entry = _to_expansion_entry(stored)
    assert expansion_entry['recurrence'] == 'annual'
    assert expansion_entry['month'] == 12
    assert expansion_entry['day'] == 25


@pytest.mark.parametrize("data,expected_date", [
    ({'title': 'Kentucky Derby', 'recurrence': 'nth_weekday', 'month': 5, 'weekday': 5, 'ordinal': 1},
     datetime(2024, 5, 4)),
    ({'title': 'Olympics', 'recurrence': 'periodic_years', 'interval_years': 4, 'anchor_year': 2024,
      'month': 7, 'day': 26}, datetime(2024, 7, 26)),
    ({'title': 'Some Festival', 'recurrence': 'seasonal', 'month': 10, 'day': 1}, datetime(2024, 10, 1)),
])
def test_validate_then_expand_round_trip_for_each_new_kind(app, data, expected_date):
    """validate_entry_input -> _to_expansion_entry -> expand_entries_for_year,
    the same chain regenerate_event_cache_for_entity runs, for each new
    recurrence kind."""
    with app.app_context():
        stored_entry = validate_entry_input(data)
        expansion_entry = _to_expansion_entry(stored_entry)
        occurrences = expand_entries_for_year([expansion_entry], 2024)
        assert occurrences[0]['date'] == expected_date
