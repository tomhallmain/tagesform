import pytest
from datetime import datetime
from unittest.mock import patch
from freezegun import freeze_time

from app.models import EventCache
from app.services.integration_service import integration_service
from app.services.calendar_aggregator import Event
from app.tasks.background_tasks import backfill_computed_calendar_events, COMPUTED_CALENDAR_BACKFILL_YEARS

pytestmark = pytest.mark.integration


def _fake_hebcal_event(year):
    return Event(name=f"Test Holiday {year}", date=datetime(year, 9, 12), source='Hebcal')


def _fake_usno_event(year):
    return Event(name="Vernal Equinox", date=datetime(year, 3, 20), source='USNO')


@pytest.fixture(autouse=True)
def mock_usno_by_default():
    """USNO is a real, network-calling source in computed_sources (unlike
    NobelPrizeSchedule, which is pure computation) -- keep it silent by
    default so tests focused on Hebcal/Nobel don't hit the network. Tests
    that actually exercise USNO override this with their own patch."""
    with patch.object(integration_service.calendar_aggregator.usno_astronomical_events_api,
                       'get_events', return_value=[]):
        yield


def test_backfill_populates_missing_years_on_first_run(app, db_session):
    with freeze_time("2026-01-01"):
        with patch.object(integration_service.calendar_aggregator.hebcal_api, 'get_events',
                           side_effect=lambda year: [_fake_hebcal_event(year)]) as mock_get_events:
            backfill_computed_calendar_events(app)

    assert mock_get_events.call_count == COMPUTED_CALENDAR_BACKFILL_YEARS

    cached_years = {row.year for row in EventCache.query.filter_by(source='Hebcal').all()}
    assert cached_years == set(range(2026, 2026 + COMPUTED_CALENDAR_BACKFILL_YEARS))


def test_backfill_is_a_no_op_on_second_run(app, db_session):
    """Once a horizon is fully cached, a second run must not re-fetch
    anything -- these dates never change once computed, so refetching them
    would be pure waste against a free public API."""
    with freeze_time("2026-01-01"):
        with patch.object(integration_service.calendar_aggregator.hebcal_api, 'get_events',
                           side_effect=lambda year: [_fake_hebcal_event(year)]):
            backfill_computed_calendar_events(app)

        with patch.object(integration_service.calendar_aggregator.hebcal_api, 'get_events') as mock_get_events:
            backfill_computed_calendar_events(app)

    mock_get_events.assert_not_called()


def test_backfill_only_fetches_the_newly_missing_tail_year_after_horizon_advances(app, db_session):
    with freeze_time("2026-01-01"):
        with patch.object(integration_service.calendar_aggregator.hebcal_api, 'get_events',
                           side_effect=lambda year: [_fake_hebcal_event(year)]):
            backfill_computed_calendar_events(app)

    with freeze_time("2027-01-01"):
        with patch.object(integration_service.calendar_aggregator.hebcal_api, 'get_events',
                           side_effect=lambda year: [_fake_hebcal_event(year)]) as mock_get_events:
            backfill_computed_calendar_events(app)

    new_tail_year = 2027 + COMPUTED_CALENDAR_BACKFILL_YEARS - 1
    mock_get_events.assert_called_once_with(new_tail_year)


def test_backfill_populates_nobel_prize_schedule_using_real_curated_data(app, db_session):
    """Exercises the real NobelPrizeSchedule (no network call, pure
    computation) through the actual backfill job -- including the naive
    previous-year fallback for years without a curated entry."""
    with freeze_time("2026-01-01"):
        with patch.object(integration_service.calendar_aggregator.hebcal_api, 'get_events', return_value=[]):
            backfill_computed_calendar_events(app)

    physics_2026 = EventCache.query.filter_by(
        source='Nobel Prize', year=2026, title='Nobel Prize in Physics Announcement'
    ).first()
    assert physics_2026 is not None
    assert physics_2026.date == datetime(2026, 10, 6)

    # 2027 has no curated entry -- naively falls back to 2026's month/day.
    physics_2027 = EventCache.query.filter_by(
        source='Nobel Prize', year=2027, title='Nobel Prize in Physics Announcement'
    ).first()
    assert physics_2027 is not None
    assert physics_2027.date == datetime(2027, 10, 6)


def test_backfill_populates_usno_astronomical_events(app, db_session):
    with freeze_time("2026-01-01"):
        with patch.object(integration_service.calendar_aggregator.hebcal_api, 'get_events', return_value=[]), \
             patch.object(integration_service.calendar_aggregator.usno_astronomical_events_api, 'get_events',
                           side_effect=lambda year: [_fake_usno_event(year)]) as mock_get_events:
            backfill_computed_calendar_events(app)

    assert mock_get_events.call_count == COMPUTED_CALENDAR_BACKFILL_YEARS

    cached_years = {row.year for row in EventCache.query.filter_by(source='USNO').all()}
    assert cached_years == set(range(2026, 2026 + COMPUTED_CALENDAR_BACKFILL_YEARS))


def test_backfill_failure_for_one_year_does_not_block_other_years(app, db_session):
    def flaky_get_events(year):
        if year == 2028:
            raise Exception("simulated failure")
        return [_fake_hebcal_event(year)]

    with freeze_time("2026-01-01"):
        with patch.object(integration_service.calendar_aggregator.hebcal_api, 'get_events',
                           side_effect=flaky_get_events):
            backfill_computed_calendar_events(app)

    cached_years = {row.year for row in EventCache.query.filter_by(source='Hebcal').all()}
    assert 2028 not in cached_years
    assert 2026 in cached_years
    assert 2029 in cached_years  # later years still attempted despite 2028 failing
