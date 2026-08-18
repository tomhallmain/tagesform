import pytest
from datetime import datetime

from app.models import DefaultEventDescriptor, EventCache, User
from app.services.default_event_service import (
    _to_expansion_entry, regenerate_event_cache_for_user_default_events, DEFAULT_EVENT_SOURCE,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def kentucky_derby(db_session):
    descriptor = DefaultEventDescriptor(
        title='Kentucky Derby', category='Sports Festival', recurrence='nth_weekday',
        recurrence_params={'month': 5, 'weekday': 5, 'ordinal': 1},
        location='Churchill Downs',
    )
    db_session.add(descriptor)
    db_session.commit()
    return descriptor


@pytest.fixture
def dripping_springs(db_session):
    """No 'day' in recurrence_params -- exercises the seasonal
    missing-day default (see expand_entries_for_year)."""
    descriptor = DefaultEventDescriptor(
        title='Dripping Springs Music Festival', category='Music Festival', recurrence='seasonal',
        recurrence_params={'month': 10},
    )
    db_session.add(descriptor)
    db_session.commit()
    return descriptor


@pytest.fixture
def other_user(db_session):
    user = User(username='other_user', email='other@example.com')
    user.set_password('password')
    db_session.add(user)
    db_session.commit()
    return user


def test_to_expansion_entry_reads_recurrence_params(app, kentucky_derby):
    with app.app_context():
        entry = _to_expansion_entry(kentucky_derby)
        assert entry['title'] == 'Kentucky Derby'
        assert entry['recurrence'] == 'nth_weekday'
        assert entry['month'] == 5
        assert entry['weekday'] == 5
        assert entry['ordinal'] == 1
        assert entry['location'] == 'Churchill Downs'


def test_to_expansion_entry_missing_params_default_to_none(app, dripping_springs):
    with app.app_context():
        entry = _to_expansion_entry(dripping_springs)
        assert entry['month'] == 10
        assert entry['day'] is None  # not set in recurrence_params -- expand_entries_for_year defaults it


def test_regenerate_creates_cache_rows_for_subscribed_descriptor(app, test_user, kentucky_derby, db_session):
    regenerate_event_cache_for_user_default_events(test_user.id, [kentucky_derby.id], years=[2024, 2028])

    cached = EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).all()
    dates = {c.date for c in cached}
    assert datetime(2024, 5, 4) in dates
    assert datetime(2028, 5, 6) in dates


def test_regenerate_with_seasonal_descriptor_uses_default_day(app, test_user, dripping_springs, db_session):
    regenerate_event_cache_for_user_default_events(test_user.id, [dripping_springs.id], years=[2026])

    cached = EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).first()
    assert cached.date == datetime(2026, 10, 1)


def test_regenerate_deletes_stale_rows_on_resubscribe(app, test_user, kentucky_derby, dripping_springs, db_session):
    regenerate_event_cache_for_user_default_events(test_user.id, [kentucky_derby.id, dripping_springs.id], years=[2026])
    assert EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).count() == 2

    # Unsubscribed from Dripping Springs, kept Kentucky Derby.
    regenerate_event_cache_for_user_default_events(test_user.id, [kentucky_derby.id], years=[2026])

    cached = EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).all()
    assert len(cached) == 1
    assert cached[0].title == 'Kentucky Derby'


def test_regenerate_with_empty_subscription_clears_everything(app, test_user, kentucky_derby, db_session):
    regenerate_event_cache_for_user_default_events(test_user.id, [kentucky_derby.id], years=[2026])
    assert EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).count() == 1

    regenerate_event_cache_for_user_default_events(test_user.id, [], years=[2026])

    assert EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).count() == 0


def test_regenerate_silently_skips_a_subscribed_id_no_longer_in_the_catalog(app, test_user, kentucky_derby, db_session):
    stale_id = kentucky_derby.id + 999  # does not exist

    # Must not raise -- a stale id is dropped, not an error.
    regenerate_event_cache_for_user_default_events(test_user.id, [kentucky_derby.id, stale_id], years=[2026])

    cached = EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).all()
    assert len(cached) == 1
    assert cached[0].title == 'Kentucky Derby'


def test_regenerate_scopes_cache_rows_to_the_subscribing_user_only(app, test_user, other_user, kentucky_derby, db_session):
    regenerate_event_cache_for_user_default_events(test_user.id, [kentucky_derby.id], years=[2026])

    assert EventCache.query.filter_by(user_id=other_user.id, source=DEFAULT_EVENT_SOURCE).count() == 0
    assert EventCache.query.filter_by(user_id=test_user.id, source=DEFAULT_EVENT_SOURCE).count() == 1
