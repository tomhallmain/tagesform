import pytest

from app.services.entity_calendar_service import validate_entry_input, EntityCalendarValidationError

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
