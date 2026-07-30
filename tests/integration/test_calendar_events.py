import pytest
from datetime import datetime
from unittest.mock import patch
from flask_login import login_user

from app.models import EventCache
from app.services.integration_service import integration_service

pytestmark = pytest.mark.integration


def test_get_calendar_events_reads_from_cache_not_live_apis(app, test_user, db_session):
    """get_calendar_events must read EventCache rather than calling the live
    CalendarAggregator -- calling the live APIs synchronously per request used
    to make every dashboard load take minutes (Inadiutorium alone issues one
    request per month)."""
    with app.app_context():
        cached = EventCache(
            title='Test Holiday',
            date=datetime(2026, 7, 30, 0, 0),
            description='desc',
            location='US',
            source='Nager Public Holidays API',
            year=2026
        )
        db_session.add(cached)
        db_session.commit()

        with app.test_request_context():
            login_user(test_user)
            with patch.object(integration_service.calendar_aggregator, 'get_events') as mock_get_events:
                events = integration_service.get_calendar_events(
                    start_date=datetime(2026, 7, 1),
                    end_date=datetime(2026, 8, 1)
                )

        mock_get_events.assert_not_called()
        assert len(events) == 1
        assert events[0]['title'] == 'Test Holiday'


def test_get_calendar_events_filters_by_date_range(app, test_user, db_session):
    with app.app_context():
        in_range = EventCache(title='In Range', date=datetime(2026, 7, 30), year=2026)
        out_of_range = EventCache(title='Out of Range', date=datetime(2027, 1, 1), year=2027)
        db_session.add_all([in_range, out_of_range])
        db_session.commit()

        with app.test_request_context():
            login_user(test_user)
            events = integration_service.get_calendar_events(
                start_date=datetime(2026, 7, 1),
                end_date=datetime(2026, 8, 1)
            )

        titles = [e['title'] for e in events]
        assert 'In Range' in titles
        assert 'Out of Range' not in titles


def test_get_calendar_events_includes_ancient_egyptian_date(app, test_user, db_session):
    """Every event returned by get_calendar_events must carry its Ancient
    Egyptian civil-calendar equivalent -- computed per-event, not just for
    'today', so it's visible across whatever day/week/month/year range this
    method is serving (see docs/egyptian-calendars.md's Part 2 Goals)."""
    from app.utils.ancient_egyptian_calendar import to_ancient_egyptian_date, format_ancient_egyptian_date

    with app.app_context():
        event_date = datetime(2026, 7, 30)
        cached = EventCache(title='Test Holiday', date=event_date, year=2026)
        db_session.add(cached)
        db_session.commit()

        with app.test_request_context():
            login_user(test_user)
            events = integration_service.get_calendar_events(
                start_date=datetime(2026, 7, 1), end_date=datetime(2026, 8, 1)
            )

        expected = format_ancient_egyptian_date(to_ancient_egyptian_date(event_date))
        assert events[0]['ancient_egyptian_date'] == expected


def test_fetch_live_calendar_events_still_calls_calendar_aggregator(app):
    """The background job's refresh path must still go through
    CalendarAggregator -- this is the one place that's allowed to hit the
    live APIs."""
    with app.app_context():
        with patch.object(integration_service.calendar_aggregator, 'get_events', return_value=[]) as mock_get_events:
            events = integration_service.fetch_live_calendar_events(
                start_date=datetime(2026, 1, 1),
                end_date=datetime(2026, 12, 31)
            )

        mock_get_events.assert_called_once()
        assert events == []
