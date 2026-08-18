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


# --- nth_weekday / periodic_years / seasonal: parse_descriptor validation ---

def test_parse_descriptor_valid_nth_weekday_entry(app):
    with app.app_context():
        entries = parse_descriptor(
            "events:\n  - title: Kentucky Derby\n    recurrence: nth_weekday\n"
            "    month: 5\n    weekday: 5\n    ordinal: 1\n"
        )
        entry = entries[0]
        assert entry['month'] == 5
        assert entry['weekday'] == 5
        assert entry['ordinal'] == 1
        assert entry['day'] is None
        assert entry['year'] is None


def test_parse_descriptor_rejects_nth_weekday_missing_weekday(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="weekday"):
            parse_descriptor("events:\n  - title: X\n    recurrence: nth_weekday\n    month: 5\n    ordinal: 1\n")


def test_parse_descriptor_rejects_nth_weekday_missing_ordinal(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="ordinal"):
            parse_descriptor("events:\n  - title: X\n    recurrence: nth_weekday\n    month: 5\n    weekday: 5\n")


@pytest.mark.parametrize("bad_ordinal", [0, 6])
def test_parse_descriptor_rejects_out_of_range_ordinal(app, bad_ordinal):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="ordinal"):
            parse_descriptor(
                f"events:\n  - title: X\n    recurrence: nth_weekday\n    month: 5\n"
                f"    weekday: 5\n    ordinal: {bad_ordinal}\n"
            )


def test_parse_descriptor_rejects_boolean_ordinal(app):
    """Same 'bool is an int subclass' trap as month/day -- True must not be
    silently treated as ordinal 1."""
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="ordinal"):
            parse_descriptor(
                "events:\n  - title: X\n    recurrence: nth_weekday\n    month: 5\n"
                "    weekday: 5\n    ordinal: true\n"
            )


def test_parse_descriptor_rejects_out_of_range_weekday(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="weekday"):
            parse_descriptor(
                "events:\n  - title: X\n    recurrence: nth_weekday\n    month: 5\n"
                "    weekday: 7\n    ordinal: 1\n"
            )


def test_parse_descriptor_valid_periodic_years_with_fixed_day(app):
    with app.app_context():
        entries = parse_descriptor(
            "events:\n  - title: Olympics\n    recurrence: periodic_years\n"
            "    interval_years: 4\n    anchor_year: 2024\n    month: 7\n    day: 26\n"
        )
        entry = entries[0]
        assert entry['interval_years'] == 4
        assert entry['anchor_year'] == 2024
        assert entry['month'] == 7
        assert entry['day'] == 26
        assert entry['weekday'] is None
        assert entry['ordinal'] is None


def test_parse_descriptor_valid_periodic_years_with_weekday_ordinal(app):
    with app.app_context():
        entries = parse_descriptor(
            "events:\n  - title: Quadrennial Thing\n    recurrence: periodic_years\n"
            "    interval_years: 4\n    anchor_year: 2024\n    month: 5\n"
            "    weekday: 0\n    ordinal: -1\n"
        )
        entry = entries[0]
        assert entry['day'] is None
        assert entry['weekday'] == 0
        assert entry['ordinal'] == -1


def test_parse_descriptor_rejects_periodic_years_missing_interval_years(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="interval_years"):
            parse_descriptor(
                "events:\n  - title: X\n    recurrence: periodic_years\n"
                "    anchor_year: 2024\n    month: 7\n    day: 26\n"
            )


def test_parse_descriptor_rejects_periodic_years_interval_below_two(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="interval_years"):
            parse_descriptor(
                "events:\n  - title: X\n    recurrence: periodic_years\n"
                "    interval_years: 1\n    anchor_year: 2024\n    month: 7\n    day: 26\n"
            )


def test_parse_descriptor_rejects_periodic_years_missing_anchor_year(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="anchor_year"):
            parse_descriptor(
                "events:\n  - title: X\n    recurrence: periodic_years\n"
                "    interval_years: 4\n    month: 7\n    day: 26\n"
            )


def test_parse_descriptor_rejects_periodic_years_with_both_day_and_weekday(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="not both"):
            parse_descriptor(
                "events:\n  - title: X\n    recurrence: periodic_years\n"
                "    interval_years: 4\n    anchor_year: 2024\n    month: 5\n"
                "    day: 1\n    weekday: 0\n    ordinal: 1\n"
            )


def test_parse_descriptor_rejects_periodic_years_with_neither_day_nor_weekday(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="require either"):
            parse_descriptor(
                "events:\n  - title: X\n    recurrence: periodic_years\n"
                "    interval_years: 4\n    anchor_year: 2024\n    month: 5\n"
            )


def test_parse_descriptor_valid_seasonal_entry_defaults_day_to_one(app):
    with app.app_context():
        entries = parse_descriptor(
            "events:\n  - title: Dripping Springs Music Festival\n    recurrence: seasonal\n    month: 10\n"
        )
        entry = entries[0]
        assert entry['month'] == 10
        assert entry['day'] == 1


def test_parse_descriptor_valid_seasonal_entry_with_explicit_day(app):
    with app.app_context():
        entries = parse_descriptor(
            "events:\n  - title: X\n    recurrence: seasonal\n    month: 10\n    day: 15\n"
        )
        assert entries[0]['day'] == 15


def test_parse_descriptor_rejects_seasonal_missing_month(app):
    with app.app_context():
        with pytest.raises(DescriptorValidationError, match="month"):
            parse_descriptor("events:\n  - title: X\n    recurrence: seasonal\n")


# --- nth_weekday / periodic_years / seasonal: expand_entries_for_year ---

def test_expand_entries_for_year_nth_weekday_resolves_first_saturday_in_may():
    """Kentucky Derby: first Saturday in May -- checked against the real
    known 2024 date (May 4), not just internal consistency."""
    entries = [{'title': 'Kentucky Derby', 'recurrence': 'nth_weekday', 'month': 5,
                'weekday': 5, 'ordinal': 1, 'description': None, 'location': None, 'year': None}]

    assert expand_entries_for_year(entries, 2024)[0]['date'] == datetime(2024, 5, 4)
    assert expand_entries_for_year(entries, 2026)[0]['date'] == datetime(2026, 5, 2)
    assert expand_entries_for_year(entries, 2027)[0]['date'] == datetime(2027, 5, 1)


def test_expand_entries_for_year_nth_weekday_ordinal_5_skips_years_without_a_fifth_occurrence():
    entries = [{'title': '5th Sunday of Feb', 'recurrence': 'nth_weekday', 'month': 2,
                'weekday': 6, 'ordinal': 5, 'description': None, 'location': None, 'year': None}]

    assert expand_entries_for_year(entries, 2026) == []  # Feb 2026 (28 days) has no 5th Sunday
    assert expand_entries_for_year(entries, 2032)[0]['date'] == datetime(2032, 2, 29)  # leap year that has one


def test_expand_entries_for_year_nth_weekday_ordinal_negative_one_resolves_last_occurrence():
    entries = [{'title': 'Last Monday in May', 'recurrence': 'nth_weekday', 'month': 5,
                'weekday': 0, 'ordinal': -1, 'description': None, 'location': None, 'year': None}]

    assert expand_entries_for_year(entries, 2024)[0]['date'] == datetime(2024, 5, 27)


def test_expand_entries_for_year_periodic_years_with_fixed_day_only_matches_interval_years():
    entries = [{'title': 'Olympics', 'recurrence': 'periodic_years', 'interval_years': 4,
                'anchor_year': 2024, 'month': 7, 'day': 26, 'weekday': None, 'ordinal': None,
                'description': None, 'location': None, 'year': None}]

    assert expand_entries_for_year(entries, 2025) == []
    assert expand_entries_for_year(entries, 2026) == []
    assert expand_entries_for_year(entries, 2028)[0]['date'] == datetime(2028, 7, 26)


def test_expand_entries_for_year_periodic_years_with_weekday_ordinal_resolves_in_matching_years():
    entries = [{'title': 'Quadrennial Thing', 'recurrence': 'periodic_years', 'interval_years': 4,
                'anchor_year': 2024, 'month': 5, 'day': None, 'weekday': 0, 'ordinal': -1,
                'description': None, 'location': None, 'year': None}]

    assert expand_entries_for_year(entries, 2026) == []
    assert expand_entries_for_year(entries, 2024)[0]['date'] == datetime(2024, 5, 27)
    assert expand_entries_for_year(entries, 2028)[0]['date'] == datetime(2028, 5, 29)


def test_expand_entries_for_year_seasonal_recurs_every_year_with_approximate_marker():
    entries = [{'title': 'Dripping Springs Music Festival', 'recurrence': 'seasonal', 'month': 10,
                'day': 1, 'description': None, 'location': None, 'year': None}]

    occurrence_2026 = expand_entries_for_year(entries, 2026)[0]
    occurrence_2027 = expand_entries_for_year(entries, 2027)[0]

    assert occurrence_2026['date'] == datetime(2026, 10, 1)
    assert occurrence_2027['date'] == datetime(2027, 10, 1)
    assert 'approximate' in occurrence_2026['description']


def test_expand_entries_for_year_seasonal_appends_marker_to_existing_description():
    entries = [{'title': 'Some Festival', 'recurrence': 'seasonal', 'month': 6, 'day': 15,
                'description': 'Annual outdoor gathering', 'location': None, 'year': None}]

    occurrence = expand_entries_for_year(entries, 2026)[0]
    assert occurrence['description'].startswith('Annual outdoor gathering')
    assert 'approximate' in occurrence['description']


def test_expand_entries_for_year_seasonal_defaults_missing_day_key_to_one():
    """parse_descriptor's validator always fills in day=1 when omitted, but
    expand_entries_for_year is also reached by callers that build entries
    directly from trusted data with no validation step (e.g.
    default_event_service.py's DB-seeded catalog rows) -- the default has
    to hold here too, for an entry that has no 'day' key at all, not only
    for entries that already went through _validate_seasonal_fields."""
    entries = [{'title': 'Some Festival', 'recurrence': 'seasonal', 'month': 10,
                'description': None, 'location': None, 'year': None}]  # no 'day' key

    assert expand_entries_for_year(entries, 2026)[0]['date'] == datetime(2026, 10, 1)
