import datetime
import pytest
from unittest.mock import patch, MagicMock

from app.services.calendar_aggregator import (
    CalendarAggregator, Event, HebcalAPI, HijriCalendarAPI, InadiutoriumAPI, LaunchLibraryAPI,
    NobelPrizeSchedule, USNOAstronomicalEventsAPI, format_event,
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
    re-fetched on that schedule. It's fetched instead by
    backfill_computed_calendar_events, via CalendarAggregator.hebcal_api
    directly."""
    aggregator = CalendarAggregator()
    assert hasattr(aggregator, 'hebcal_api')
    assert isinstance(aggregator.hebcal_api, HebcalAPI)

    with patch.object(aggregator.public_holidays_api, 'get_events', return_value=[]), \
         patch.object(aggregator.hijri_calendar_api, 'get_events', return_value=[]), \
         patch.object(aggregator.launch_library_api, 'get_events', return_value=[]), \
         patch.object(aggregator.hebcal_api, 'get_events') as mock_hebcal_get_events:
        aggregator.get_events(2026)

    mock_hebcal_get_events.assert_not_called()


def test_calendar_aggregator_does_not_merge_inadiutorium_into_get_events():
    """Inadiutorium (Roman Catholic liturgical calendar) must NOT be part of
    the merged get_events() aggregate -- it's computed from fixed rules (the
    Easter computus), not live-changing data, so it's fetched instead by
    backfill_computed_calendar_events, via
    CalendarAggregator.inadiutorium_api directly. This also cuts real load
    against Inadiutorium's slow remote server (~20s per monthly call)."""
    aggregator = CalendarAggregator()
    assert hasattr(aggregator, 'inadiutorium_api')
    assert isinstance(aggregator.inadiutorium_api, InadiutoriumAPI)

    with patch.object(aggregator.public_holidays_api, 'get_events', return_value=[]), \
         patch.object(aggregator.hijri_calendar_api, 'get_events', return_value=[]), \
         patch.object(aggregator.launch_library_api, 'get_events', return_value=[]), \
         patch.object(aggregator.inadiutorium_api, 'get_events') as mock_get_events:
        aggregator.get_events(2026)

    mock_get_events.assert_not_called()


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


def test_nobel_prize_schedule_uses_curated_dates_for_a_listed_year():
    schedule = NobelPrizeSchedule()

    events = schedule.get_events(2026)

    by_name = {e.name: e.date for e in events}
    assert by_name['Nobel Prize in Physics Announcement'] == datetime.datetime(2026, 10, 6)
    assert by_name['Nobel Prize in Peace Announcement'] == datetime.datetime(2026, 10, 9)
    assert all(e.sources == ['Nobel Prize'] for e in events)


def test_nobel_prize_schedule_falls_back_to_previous_curated_year(monkeypatch):
    """A year with no curated entry must naively reuse the most recent
    earlier curated year's month/day, applied to the requested year."""
    schedule = NobelPrizeSchedule()
    monkeypatch.setattr(schedule, 'SCHEDULE', {2026: {'Physics': (10, 6)}})

    events = schedule.get_events(2027)

    assert len(events) == 1
    assert events[0].date == datetime.datetime(2027, 10, 6)


def test_nobel_prize_schedule_fallback_cascades_across_multiple_uncurated_years(monkeypatch):
    """Two years past the last curated entry must still fall back to it --
    not just the immediately-preceding year -- since nothing ever
    back-fills the SCHEDULE dict itself."""
    schedule = NobelPrizeSchedule()
    monkeypatch.setattr(schedule, 'SCHEDULE', {2026: {'Physics': (10, 6)}})

    events = schedule.get_events(2028)

    assert len(events) == 1
    assert events[0].date == datetime.datetime(2028, 10, 6)


def test_nobel_prize_schedule_returns_empty_list_with_no_curated_year_at_or_before_target(monkeypatch):
    schedule = NobelPrizeSchedule()
    monkeypatch.setattr(schedule, 'SCHEDULE', {2026: {'Physics': (10, 6)}})

    assert schedule.get_events(2025) == []


def test_calendar_aggregator_does_not_merge_nobel_prize_schedule_into_get_events():
    """Same reasoning as Hebcal: this is computed/curated data, not
    something to refresh on update_event_cache's tight cycle."""
    aggregator = CalendarAggregator()
    assert hasattr(aggregator, 'nobel_prize_schedule')
    assert isinstance(aggregator.nobel_prize_schedule, NobelPrizeSchedule)

    with patch.object(aggregator.public_holidays_api, 'get_events', return_value=[]), \
         patch.object(aggregator.hijri_calendar_api, 'get_events', return_value=[]), \
         patch.object(aggregator.launch_library_api, 'get_events', return_value=[]), \
         patch.object(aggregator.nobel_prize_schedule, 'get_events') as mock_get_events:
        aggregator.get_events(2026)

    mock_get_events.assert_not_called()


def test_from_usno_season_api_parses_phenom_and_date():
    item = {"year": 2026, "month": 3, "day": 20, "phenom": "Equinox", "time": "12:46"}

    event = Event.from_usno_season_api(item)

    assert event.name == "Equinox"
    assert event.date == datetime.datetime(2026, 3, 20)
    assert event.sources == ["USNO"]


def test_from_usno_eclipse_api_parses_event_description_and_date():
    item = {"year": 2026, "month": 2, "day": 17, "event": "Annular Solar Eclipse"}

    event = Event.from_usno_eclipse_api(item)

    assert event.name == "Annular Solar Eclipse"
    assert event.date == datetime.datetime(2026, 2, 17)


def test_from_usno_moon_phase_api_parses_phase_and_date():
    item = {"year": 2026, "month": 1, "day": 3, "phase": "Full Moon", "time": "05:03"}

    event = Event.from_usno_moon_phase_api(item)

    assert event.name == "Full Moon"
    assert event.date == datetime.datetime(2026, 1, 3)


def test_usno_get_events_aggregates_all_three_endpoints_and_passes_timeout():
    api = USNOAstronomicalEventsAPI()

    def fake_get(url, params=None, timeout=None):
        assert timeout is not None
        if url.endswith('/seasons'):
            return _fake_response({"data": [
                {"year": 2026, "month": 3, "day": 20, "phenom": "Equinox", "time": "12:46"}
            ]})
        if url.endswith('/eclipses/solar/year'):
            return _fake_response({"eclipses_in_year": [
                {"year": 2026, "month": 2, "day": 17, "event": "Annular Solar Eclipse"}
            ]})
        if url.endswith('/moon/phases/year'):
            return _fake_response({"phasedata": [
                {"year": 2026, "month": 1, "day": 3, "phase": "Full Moon", "time": "05:03"}
            ]})
        raise AssertionError(f"Unexpected URL: {url}")

    with patch("app.services.calendar_aggregator.requests.get", side_effect=fake_get):
        events = api.get_events(year=2026)

    assert {e.name for e in events} == {"Equinox", "Annular Solar Eclipse", "Full Moon"}


def test_calendar_aggregator_does_not_merge_usno_into_get_events():
    """Same reasoning as Hebcal/Nobel: computed/deterministic data belongs
    in the backfill job, not update_event_cache's tight recurring cycle."""
    aggregator = CalendarAggregator()
    assert hasattr(aggregator, 'usno_astronomical_events_api')
    assert isinstance(aggregator.usno_astronomical_events_api, USNOAstronomicalEventsAPI)

    with patch.object(aggregator.public_holidays_api, 'get_events', return_value=[]), \
         patch.object(aggregator.hijri_calendar_api, 'get_events', return_value=[]), \
         patch.object(aggregator.launch_library_api, 'get_events', return_value=[]), \
         patch.object(aggregator.usno_astronomical_events_api, 'get_events') as mock_get_events:
        aggregator.get_events(2026)

    mock_get_events.assert_not_called()


def test_from_launch_library_api_parses_name_and_strips_timezone():
    """The Launch Library 'net' field is ISO 8601 with a trailing 'Z'
    (timezone-aware). Event.date must come out naive -- every other Event
    in this module is naive, and mixing naive/aware datetimes raises a
    TypeError the moment CalendarAggregator.get_events() sorts them
    together."""
    item = {
        "name": "Falcon 9 Block 5 | Starlink Group 17-52",
        "net": "2026-08-01T02:00:00Z",
        "status": {"id": 1, "name": "Go"},
        "mission": {"description": "Starlink satellite deployment"},
    }

    event = Event.from_launch_library_api(item)

    assert event.name == "Falcon 9 Block 5 | Starlink Group 17-52"
    assert event.date == datetime.datetime(2026, 8, 1, 2, 0, 0)
    assert event.date.tzinfo is None
    assert event.sources == ["Launch Library"]


def test_launch_library_get_events_requests_upcoming_with_a_large_limit_and_timeout():
    """Must not mirror the 'fetch a whole year' pattern the other live
    sources use -- Launch Library's free tier is capped at 15 requests/hour,
    and paging through two years of global launches could blow through that
    in a single job run. A single call with a large limit keeps this well
    under budget."""
    api = LaunchLibraryAPI()

    with patch("app.services.calendar_aggregator.requests.get",
               return_value=_fake_response({"results": []})) as mock_get:
        api.get_events(year=2026)

    mock_get.assert_called_once()
    call = mock_get.call_args
    assert call.args[0] == LaunchLibraryAPI.BASE_URL
    assert call.kwargs.get("params", {}).get("limit") == LaunchLibraryAPI.PAGE_LIMIT
    assert call.kwargs.get("timeout") is not None


def test_calendar_aggregator_merges_launch_library_into_get_events():
    """Unlike Hebcal/USNO/Nobel, Launch Library IS live/changeable data
    (launches slip and get scrubbed constantly), so it belongs in the
    merged get_events() aggregate refreshed by update_event_cache."""
    aggregator = CalendarAggregator()
    assert hasattr(aggregator, 'launch_library_api')
    assert isinstance(aggregator.launch_library_api, LaunchLibraryAPI)

    with patch.object(aggregator.public_holidays_api, 'get_events', return_value=[]), \
         patch.object(aggregator.hijri_calendar_api, 'get_events', return_value=[]), \
         patch.object(aggregator.launch_library_api, 'get_events', return_value=[]) as mock_get_events:
        aggregator.get_events(2026)

    mock_get_events.assert_called_once()
