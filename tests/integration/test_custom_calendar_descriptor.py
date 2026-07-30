import pytest
from datetime import datetime
from unittest.mock import patch
from flask_login import login_user
from freezegun import freeze_time

from app.models import EventCache, UserCalendarDescriptor, User
from app.services.integration_service import integration_service
from app.tasks.background_tasks import update_event_cache

pytestmark = pytest.mark.integration

VALID_YAML = """
events:
  - title: "Mom's Birthday"
    recurrence: annual
    month: 4
    day: 12
  - title: "Anniversary Trip"
    recurrence: once
    date: 2026-09-14
"""


def test_save_calendar_descriptor_creates_descriptor_and_cache_rows(client, auth, test_user, db_session):
    auth.login()

    with freeze_time("2026-07-30"):
        response = client.post('/settings/update-calendar-descriptor', data={'raw_yaml': VALID_YAML})
        assert response.status_code == 302

    descriptor = UserCalendarDescriptor.query.filter_by(user_id=test_user.id).first()
    assert descriptor is not None
    assert descriptor.last_parse_error is None

    cached = EventCache.query.filter_by(user_id=test_user.id, source='Custom Calendar').all()
    titles = {c.title for c in cached}
    assert "Mom's Birthday" in titles
    assert 'Anniversary Trip' in titles

    # The annual entry should be expanded into both the current and next year.
    birthday_years = {c.year for c in cached if c.title == "Mom's Birthday"}
    assert birthday_years == {2026, 2027}

    # The 'once' entry only belongs to its own year.
    trip_years = {c.year for c in cached if c.title == 'Anniversary Trip'}
    assert trip_years == {2026}


def test_save_calendar_descriptor_rejects_invalid_yaml_without_saving(client, auth, test_user, db_session):
    auth.login()

    response = client.post('/settings/update-calendar-descriptor', data={'raw_yaml': 'events: not-a-list'})
    assert response.status_code == 302  # flash + redirect, not a hard error page

    assert UserCalendarDescriptor.query.filter_by(user_id=test_user.id).first() is None


def test_save_calendar_descriptor_does_not_overwrite_previous_valid_file_on_failed_reupload(client, auth, test_user, db_session):
    auth.login()
    client.post('/settings/update-calendar-descriptor', data={'raw_yaml': VALID_YAML})

    response = client.post('/settings/update-calendar-descriptor', data={'raw_yaml': 'events: not-a-list'})
    assert response.status_code == 302

    descriptor = UserCalendarDescriptor.query.filter_by(user_id=test_user.id).first()
    assert descriptor.raw_yaml == VALID_YAML  # untouched by the failed re-upload attempt

    cached = EventCache.query.filter_by(user_id=test_user.id, source='Custom Calendar').all()
    assert len(cached) > 0  # still-cached events from the earlier valid save


def test_save_calendar_descriptor_ajax_returns_json_error(client, auth, test_user, db_session):
    auth.login()

    response = client.post(
        '/settings/update-calendar-descriptor',
        data={'raw_yaml': 'events: not-a-list'},
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_delete_calendar_descriptor_removes_descriptor_and_cache(client, auth, test_user, db_session):
    auth.login()
    client.post('/settings/update-calendar-descriptor', data={'raw_yaml': VALID_YAML})

    response = client.post('/settings/delete-calendar-descriptor')
    assert response.status_code == 302

    assert UserCalendarDescriptor.query.filter_by(user_id=test_user.id).first() is None
    assert EventCache.query.filter_by(user_id=test_user.id, source='Custom Calendar').first() is None


def test_get_calendar_events_includes_own_custom_entries_but_not_another_users(app, test_user, db_session):
    other_user = User(username='other_user', email='other@example.com')
    other_user.set_password('password')
    db_session.add(other_user)
    db_session.commit()

    db_session.add_all([
        EventCache(title='My Custom Event', date=datetime(2026, 7, 30), year=2026,
                   source='Custom Calendar', user_id=test_user.id),
        EventCache(title="Other User's Event", date=datetime(2026, 7, 30), year=2026,
                   source='Custom Calendar', user_id=other_user.id),
        EventCache(title='Public Holiday', date=datetime(2026, 7, 30), year=2026,
                   source='Nager Public Holidays API', user_id=None),
    ])
    db_session.commit()

    with app.test_request_context():
        login_user(test_user)
        events = integration_service.get_calendar_events(
            start_date=datetime(2026, 7, 1), end_date=datetime(2026, 8, 1)
        )

    titles = {e['title'] for e in events}
    assert 'My Custom Event' in titles
    assert 'Public Holiday' in titles
    assert "Other User's Event" not in titles


def test_background_job_refreshes_annual_entry_into_next_year(app, test_user, db_session):
    descriptor = UserCalendarDescriptor(user_id=test_user.id, raw_yaml=VALID_YAML)
    db_session.add(descriptor)
    db_session.commit()
    # update_event_cache pushes its own app context (it must, to run standalone
    # under APScheduler) -- when that nested context tears down, Flask-SQLAlchemy's
    # teardown hook calls db.session.remove(), detaching any ORM objects already
    # fetched in this test. Capture the plain id now; re-query fresh afterward.
    user_id = test_user.id

    with patch.object(integration_service, 'fetch_live_calendar_events', return_value=[]):
        with freeze_time("2027-01-01"):
            update_event_cache(app)

    cached_years = {
        c.year for c in EventCache.query.filter_by(
            user_id=user_id, source='Custom Calendar', title="Mom's Birthday"
        ).all()
    }
    assert 2028 in cached_years  # rolled forward without the user re-saving anything


def test_background_job_one_users_broken_descriptor_does_not_block_others(app, test_user, db_session):
    other_user = User(username='other_user', email='other@example.com')
    other_user.set_password('password')
    db_session.add(other_user)
    db_session.commit()

    broken = UserCalendarDescriptor(user_id=test_user.id, raw_yaml='events: not-a-list')
    good = UserCalendarDescriptor(user_id=other_user.id, raw_yaml=VALID_YAML)
    db_session.add_all([broken, good])
    db_session.commit()
    # See the comment in test_background_job_refreshes_annual_entry_into_next_year --
    # capture ids now, since update_event_cache's internal app context teardown
    # detaches these ORM instances from the session.
    broken_id = broken.id
    other_user_id = other_user.id

    with patch.object(integration_service, 'fetch_live_calendar_events', return_value=[]):
        update_event_cache(app)

    broken = db_session.get(UserCalendarDescriptor, broken_id)
    assert broken.last_parse_error is not None

    good_cached = EventCache.query.filter_by(user_id=other_user_id, source='Custom Calendar').all()
    assert len(good_cached) > 0
