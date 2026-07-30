import datetime
import pytest
from unittest.mock import patch, MagicMock

from app.services.calendar_aggregator import Event, HijriCalendarAPI

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
