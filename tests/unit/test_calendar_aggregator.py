import datetime
import pytest
from unittest.mock import patch, MagicMock

from app.services.calendar_aggregator import (
    CalendarAggregator, Event, HebcalAPI, HijriCalendarAPI, format_event,
)

pytestmark = pytest.mark.unit


def _fake_response(payload):
    mock_response = MagicMock()
    mock_response.json.return_value = payload
    return mock_response


def test_from_hijri_api_reads_holiday_name_from_nested_hijri_key():
    """Event.from_hijri_api must read the holiday name from event['hijri']['holidays'],
    not a top-level 'holidays' key -- the Aladhan response only nests 'holidays'
    under 'hijri', so reading it at the top level raised a KeyError: 'holidays' in
    production (the fix this test covers)."""
    event = {
        "hijri": {"date": "10-07-1447", "holidays": ["Ashura"]},
        "gregorian": {"date": "2026-01-01"},
    }

    result = Event.from_hijri_api(event)

    assert result.name == "Ashura"
    assert result.date == datetime.datetime(2026, 1, 1)


def test_hijri_get_events_requests_month_then_year_in_url():
    """get_events(year) must call get_events_for_month with (month, year) in that
    order. It previously called get_events_for_month(year, month + 1) against a
    method signature of (month, year), silently swapping the values into the
    wrong slots and building a URL like '.../gToHCalendar/2026/1' instead of the
    intended '.../gToHCalendar/1/2026'."""
    api = HijriCalendarAPI()
    requested_urls = []

    def fake_get(url, timeout=None):
        requested_urls.append(url)
        return _fake_response({"data": []})

    with patch("app.services.calendar_aggregator.requests.get", side_effect=fake_get):
        api.get_events(year=2026)

    assert requested_urls[0].endswith("gToHCalendar/1/2026")
    assert requested_urls[-1].endswith("gToHCalendar/12/2026")


def test_hijri_get_events_for_month_passes_a_timeout():
    """A hanging upstream API must not be able to block the caller indefinitely --
    every requests.get() call in this module needs an explicit timeout."""
    api = HijriCalendarAPI()

    with patch("app.services.calendar_aggregator.requests.get",
               return_value=_fake_response({"data": []})) as mock_get:
        api.get_events_for_month(1, 2026)

    assert mock_get.call_args.kwargs.get("timeout") is not None


def test_from_hebcal_api_parses_title_date_and_hebrew_name():
    event = {"title": "Rosh Hashana", "date": "2026-09-12", "category": "holiday", "hebrew": "ראש השנה"}

    result = Event.from_hebcal_api(event)

    assert result.name == "Rosh Hashana"
    assert result.date == datetime.datetime(2026, 9, 12)
    assert result.sources == ["Hebcal"]
    assert "ראש השנה" in result.other_names


def test_hebcal_get_events_parses_items_and_passes_timeout():
    payload = {"items": [
        {"title": "Rosh Hashana", "date": "2026-09-12", "category": "holiday"},
        {"title": "Yom Kippur", "date": "2026-09-21", "category": "holiday"},
    ]}
    api = HebcalAPI()

    with patch("app.services.calendar_aggregator.requests.get",
               return_value=_fake_response(payload)) as mock_get:
        events = api.get_events(year=2026)

    assert [e.name for e in events] == ["Rosh Hashana", "Yom Kippur"]
    assert mock_get.call_args.kwargs.get("timeout") is not None


def test_hebcal_get_events_handles_missing_items_key():
    api = HebcalAPI()

    with patch("app.services.calendar_aggregator.requests.get", return_value=_fake_response({})):
        events = api.get_events(year=2026)

    assert events == []


def test_calendar_aggregator_does_not_merge_hebcal_into_get_events():
    """Hebcal must NOT be part of the merged get_events() aggregate --
    that method is only ever called from the update_event_cache background
    job's tight recurring cadence, and Hebrew calendar dates shouldn't be
    re-fetched on that schedule (see docs/hebrew-calendar.md's Caching
    strategy). It's fetched instead by backfill_computed_calendar_events,
    via CalendarAggregator.hebcal_api directly."""
    aggregator = CalendarAggregator()
    assert hasattr(aggregator, 'hebcal_api')
    assert isinstance(aggregator.hebcal_api, HebcalAPI)

    with patch.object(aggregator.public_holidays_api, 'get_events', return_value=[]), \
         patch.object(aggregator.inadiutorium_api, 'get_events', return_value=[]), \
         patch.object(aggregator.hijri_calendar_api, 'get_events', return_value=[]), \
         patch.object(aggregator.hebcal_api, 'get_events') as mock_hebcal_get_events:
        aggregator.get_events(2026)

    mock_hebcal_get_events.assert_not_called()


def test_format_event_produces_expected_shape():
    event = Event(name="Test Event", date=datetime.datetime(2026, 7, 30, 0, 0),
                  source="Hebcal", country="US", notes=["a note"])

    formatted = format_event(event)

    assert formatted == {
        'title': 'Test Event',
        'start_time': '2026-07-30 00:00',
        'description': 'a note',
        'location': 'US',
        'sources': ['Hebcal'],
    }
