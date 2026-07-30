import pytest
from datetime import datetime

from app.services.custom_calendar_service import (
    parse_descriptor, expand_entries_for_year, DescriptorValidationError,
    MAX_ENTRIES, MAX_RAW_YAML_BYTES,
)

pytestmark = pytest.mark.unit


def test_parse_descriptor_valid_once_and_annual_entries(app):
    with app.app_context():
        raw_yaml = """
events:
  - title: "Mom's Birthday"
    recurrence: annual
    month: 4
    day: 12
    description: "Call in the morning"
  - title: "Anniversary Trip"
    recurrence: once
    date: 2026-09-14
    location: "LIS"
"""
        entries = parse_descriptor(raw_yaml)

        assert len(entries) == 2
        birthday, trip = entries
        assert birthday['title'] == "Mom's Birthday"
        assert birthday['recurrence'] == 'annual'
        assert birthday['month'] == 4
        assert birthday['day'] == 12
        assert birthday['description'] == "Call in the morning"

        assert trip['title'] == 'Anniversary Trip'
        assert trip['recurrence'] == 'once'
        assert trip['year'] == 2026
        assert trip['month'] == 9
        assert trip['day'] == 14
        assert trip['location'] == 'LIS'


def test_parse_descriptor_rejects_malformed_yaml(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError):
            parse_descriptor("events: [1, 2")  # unterminated flow sequence


def test_parse_descriptor_rejects_missing_title(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="title"):
            parse_descriptor("events:\n  - recurrence: once\n    date: 2026-01-01\n")


def test_parse_descriptor_rejects_invalid_recurrence(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="recurrence"):
            parse_descriptor("events:\n  - title: Test\n    recurrence: monthly\n")


def test_parse_descriptor_rejects_out_of_range_month(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="month"):
            parse_descriptor("events:\n  - title: Test\n    recurrence: annual\n    month: 13\n    day: 1\n")


def test_parse_descriptor_rejects_invalid_day_for_month(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="day"):
            parse_descriptor("events:\n  - title: Test\n    recurrence: annual\n    month: 4\n    day: 31\n")


def test_parse_descriptor_rejects_boolean_month(app):
    """YAML 'month: true' parses to Python True, which is an int subclass --
    must be rejected rather than silently treated as month 1."""
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="month"):
            parse_descriptor("events:\n  - title: Test\n    recurrence: annual\n    month: true\n    day: 1\n")


def test_parse_descriptor_allows_feb_29_annual(app):
    with app.app_context():
        entries = parse_descriptor("events:\n  - title: Leap Day\n    recurrence: annual\n    month: 2\n    day: 29\n")
        assert entries[0]['day'] == 29


def test_parse_descriptor_rejects_too_many_entries(app):
    with app.app_context():
        lines = ["events:"]
        for i in range(MAX_ENTRIES + 1):
            lines.append(f"  - title: Entry{i}\n    recurrence: once\n    date: 2026-01-01")
        with pytest.raises(DescriptorValidationError, match="Too many"):
            parse_descriptor("\n".join(lines))


def test_parse_descriptor_rejects_oversized_file(app):
    with app.app_context():
        raw_yaml = "events:\n" + ("  # padding\n" * (MAX_RAW_YAML_BYTES // 10 + 100))
        with pytest.raises(DescriptorValidationError, match="too large"):
            parse_descriptor(raw_yaml)


def test_parse_descriptor_rejects_unsafe_yaml_tags(app):
    """A malicious payload using !!python/object must not be deserialized --
    this proves yaml.safe_load is actually in effect, not yaml.load/FullLoader."""
    with app.app_context():
        malicious_yaml = """
events:
  - title: !!python/object/apply:os.system ["echo pwned"]
    recurrence: once
    date: 2026-01-01
"""
        with pytest.raises(DescriptorValidationError):
            parse_descriptor(malicious_yaml)


def test_expand_entries_for_year_annual_recurs_every_year():
    entries = [{'title': 'Birthday', 'recurrence': 'annual', 'month': 4, 'day': 12,
                'description': None, 'location': None, 'year': None}]

    occurrences_2026 = expand_entries_for_year(entries, 2026)
    occurrences_2027 = expand_entries_for_year(entries, 2027)

    assert occurrences_2026[0]['date'] == datetime(2026, 4, 12)
    assert occurrences_2027[0]['date'] == datetime(2027, 4, 12)


def test_expand_entries_for_year_once_only_appears_in_its_own_year():
    entries = [{'title': 'Trip', 'recurrence': 'once', 'month': 9, 'day': 14,
                'description': None, 'location': None, 'year': 2026}]

    assert len(expand_entries_for_year(entries, 2026)) == 1
    assert len(expand_entries_for_year(entries, 2027)) == 0


def test_expand_entries_for_year_feb_29_falls_back_to_feb_28_in_non_leap_years():
    entries = [{'title': 'Leap Day', 'recurrence': 'annual', 'month': 2, 'day': 29,
                'description': None, 'location': None, 'year': None}]

    occurrences_2027 = expand_entries_for_year(entries, 2027)  # not a leap year
    occurrences_2028 = expand_entries_for_year(entries, 2028)  # a leap year

    assert occurrences_2027[0]['date'] == datetime(2027, 2, 28)
    assert occurrences_2028[0]['date'] == datetime(2028, 2, 29)
