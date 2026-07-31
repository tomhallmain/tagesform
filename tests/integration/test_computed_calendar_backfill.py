import pytest
from datetime import datetime
from unittest.mock import patch
from freezegun import freeze_time

from app.models import EventCache
from app.services.integration_service import integration_service
from app.services.calendar_aggregator import Event
from app.tasks.background_tasks import (
    backfill_computed_calendar_events, update_event_cache, COMPUTED_CALENDAR_BACKFILL_YEARS,
)

pytestmark = pytest.mark.integration


def _fake_hebcal_event(year):
    return Event(name=f"Test Holiday {year}", date=datetime(year, 9, 12), source='Hebcal')


def _fake_usno_event(year):
    return Event(name="Vernal Equinox", date=datetime(year, 3, 20), source='USNO')


def _fake_inadiutorium_event(year):
    return Event(name="Test Feast", date=datetime(year, 12, 25), source='Inadiutorium API')


@pytest.fixture(autouse=True)
def mock_usno_by_default():
    """USNO is a real, network-calling source in computed_sources (unlike
    NobelPrizeSchedule, which is pure computation) -- keep it silent by
    default so tests focused on Hebcal/Nobel don't hit the network. Tests
    that actually exercise USNO override this with their own patch."""
    with patch.object(integration_service.calendar_aggregator.usno_astronomical_events_api,
                       'get_events', return_value=[]):
        yield


@pytest.fixture(autouse=True)
def mock_inadiutorium_by_default():
    """Same reasoning as mock_usno_by_default -- Inadiutorium makes a real
    network call per month (12 per year) and is now part of
    computed_sources, so every test in this file would otherwise try to
    hit it for the whole backfill horizon."""
    with patch.object(integration_service.calendar_aggregator.inadiutorium_api,
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


def test_backfill_populates_inadiutorium_liturgical_calendar(app, db_session):
    with freeze_time("2026-01-01"):
        with patch.object(integration_service.calendar_aggregator.hebcal_api, 'get_events', return_value=[]), \
             patch.object(integration_service.calendar_aggregator.inadiutorium_api, 'get_events',
                           side_effect=lambda year: [_fake_inadiutorium_event(year)]) as mock_get_events:
            backfill_computed_calendar_events(app)

    assert mock_get_events.call_count == COMPUTED_CALENDAR_BACKFILL_YEARS

    cached_years = {row.year for row in EventCache.query.filter_by(source='Inadiutorium API').all()}
    assert cached_years == set(range(2026, 2026 + COMPUTED_CALENDAR_BACKFILL_YEARS))


def test_update_event_cache_does_not_wipe_computed_calendar_rows(app, db_session):
    """update_event_cache's per-year cache refresh must exclude computed
    sources (Hebcal/USNO/Nobel Prize/Inadiutorium) from its blanket delete
    of that year's global rows -- it never reinserts them
    (fetch_live_calendar_events doesn't return them), so without this
    exclusion a naive delete-by-year would silently wipe them out until the
    next backfill_computed_calendar_events run restores them."""
    for source in ('Hebcal', 'USNO', 'Nobel Prize', 'Inadiutorium API'):
        db_session.add(EventCache(title=f'{source} Event', date=datetime(2026, 9, 12), year=2026, source=source))
    db_session.commit()

    with patch.object(integration_service, 'fetch_live_calendar_events', return_value=[]):
        update_event_cache(app)

    for source in ('Hebcal', 'USNO', 'Nobel Prize', 'Inadiutorium API'):
        assert EventCache.query.filter_by(source=source, year=2026).count() == 1


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
