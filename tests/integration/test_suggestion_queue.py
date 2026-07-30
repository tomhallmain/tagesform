import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from freezegun import freeze_time

from app.models import Activity, Entity, EventCache, SuggestionQueueItem, User
from app.services.suggestion_queue_service import refresh_queue_for_user
from app.tasks.background_tasks import refresh_suggestion_queue

pytestmark = pytest.mark.integration


def _create_other_user(db_session, username='other_user', email='other@example.com'):
    user = User(username=username, email=email)
    user.set_password('password')
    db_session.add(user)
    db_session.commit()
    return user


# ---- refresh_queue_for_user ----

def test_refresh_queue_creates_items_from_candidates(app, test_user, db_session):
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        activity = Activity(title='Test Activity', scheduled_time=now + timedelta(hours=2),
                             status='upcoming', user_id=test_user.id)
        db_session.add(activity)
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)

        item = SuggestionQueueItem.query.filter_by(
            user_id=test_user.id, item_type='activity', source_id=activity.id
        ).first()
        assert item is not None
        assert item.title == 'Test Activity'
        assert item.status == 'pending'


def test_refresh_queue_upserts_rather_than_duplicates_on_second_run(app, test_user, db_session):
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        activity = Activity(title='Test Activity', scheduled_time=now + timedelta(hours=2),
                             status='upcoming', importance=0.5, user_id=test_user.id)
        db_session.add(activity)
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)
        activity.importance = 0.9
        db_session.commit()
        refresh_queue_for_user(test_user, now=now)

        items = SuggestionQueueItem.query.filter_by(
            user_id=test_user.id, item_type='activity', source_id=activity.id
        ).all()
        assert len(items) == 1
        assert items[0].score > 0.5  # picked up the higher importance on refresh


def test_refresh_queue_preserves_dismissed_status_across_refresh(app, test_user, db_session):
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        activity = Activity(title='Test Activity', scheduled_time=now + timedelta(hours=2),
                             status='upcoming', user_id=test_user.id)
        db_session.add(activity)
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)
        item = SuggestionQueueItem.query.filter_by(user_id=test_user.id, item_type='activity').first()
        item.status = 'dismissed'
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)

        item = SuggestionQueueItem.query.filter_by(user_id=test_user.id, item_type='activity').first()
        assert item.status == 'dismissed'


def test_refresh_queue_auto_expires_passed_snooze(app, test_user, db_session):
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        activity = Activity(title='Test Activity', scheduled_time=now + timedelta(hours=2),
                             status='upcoming', user_id=test_user.id)
        db_session.add(activity)
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)
        item = SuggestionQueueItem.query.filter_by(user_id=test_user.id, item_type='activity').first()
        item.status = 'snoozed'
        item.snoozed_until = now - timedelta(hours=1)  # already passed
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)

        item = SuggestionQueueItem.query.filter_by(user_id=test_user.id, item_type='activity').first()
        assert item.status == 'pending'
        assert item.snoozed_until is None


def test_refresh_queue_keeps_snoozed_items_snoozed_until_expiry(app, test_user, db_session):
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        activity = Activity(title='Test Activity', scheduled_time=now + timedelta(hours=2),
                             status='upcoming', user_id=test_user.id)
        db_session.add(activity)
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)
        item = SuggestionQueueItem.query.filter_by(user_id=test_user.id, item_type='activity').first()
        item.status = 'snoozed'
        item.snoozed_until = now + timedelta(hours=1)  # not yet passed
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)

        item = SuggestionQueueItem.query.filter_by(user_id=test_user.id, item_type='activity').first()
        assert item.status == 'snoozed'


def test_refresh_queue_prunes_item_for_deleted_activity(app, test_user, db_session):
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        activity = Activity(title='Test Activity', scheduled_time=now + timedelta(hours=2),
                             status='upcoming', user_id=test_user.id)
        db_session.add(activity)
        db_session.commit()
        activity_id = activity.id

        refresh_queue_for_user(test_user, now=now)
        assert SuggestionQueueItem.query.filter_by(item_type='activity', source_id=activity_id).first() is not None

        db_session.delete(activity)
        db_session.commit()
        refresh_queue_for_user(test_user, now=now)

        assert SuggestionQueueItem.query.filter_by(item_type='activity', source_id=activity_id).first() is None


def test_refresh_queue_prunes_dismissed_item_once_its_source_no_longer_qualifies(app, test_user, db_session):
    """Pruning must apply regardless of status -- a dismissed item for a
    since-deleted activity is dead weight, not a user decision worth
    preserving indefinitely."""
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        activity = Activity(title='Test Activity', scheduled_time=now + timedelta(hours=2),
                             status='upcoming', user_id=test_user.id)
        db_session.add(activity)
        db_session.commit()
        activity_id = activity.id

        refresh_queue_for_user(test_user, now=now)
        item = SuggestionQueueItem.query.filter_by(item_type='activity', source_id=activity_id).first()
        item.status = 'dismissed'
        db_session.commit()

        db_session.delete(activity)
        db_session.commit()
        refresh_queue_for_user(test_user, now=now)

        assert SuggestionQueueItem.query.filter_by(item_type='activity', source_id=activity_id).first() is None


def test_refresh_queue_includes_event_candidates_from_event_cache(app, test_user, db_session):
    """Confirms the integration point with the calendar work: an EventCache
    row (global, custom-calendar, or entity-calendar sourced -- doesn't
    matter which, get_calendar_events already merges them all) becomes an
    'event' queue candidate."""
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        cached = EventCache(title='Upcoming Holiday', date=now + timedelta(days=2), year=2026,
                             source='Nager Public Holidays API')
        db_session.add(cached)
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)

        item = SuggestionQueueItem.query.filter_by(
            user_id=test_user.id, item_type='event', source_id=cached.id
        ).first()
        assert item is not None
        assert item.title == 'Upcoming Holiday'


def test_refresh_queue_does_not_include_another_users_private_event(app, test_user, db_session):
    other_user = _create_other_user(db_session)
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        private_place = Entity(name='Other Place', category='restaurant', is_public=False, user_id=other_user.id)
        db_session.add(private_place)
        db_session.commit()

        cached = EventCache(title='Hidden Closure', date=now + timedelta(days=2), year=2026,
                             source='Entity Calendar', entity_id=private_place.id)
        db_session.add(cached)
        db_session.commit()

        refresh_queue_for_user(test_user, now=now)

        assert SuggestionQueueItem.query.filter_by(
            user_id=test_user.id, item_type='event', source_id=cached.id
        ).first() is None


# ---- API endpoints ----
#
# No `with app.app_context():` wrapping here, deliberately -- the session-scoped
# `app` fixture already keeps an app context pushed for the whole test session
# (same convention as test_entity_comments.py/test_entity_calendar.py). An
# extra nested context here would pop (and tear down) at the end of its `with`
# block, and that teardown fires Flask-SQLAlchemy's db.session.remove() --
# which corrupts current_user's resolution on the *next* request in the same
# test, since current_user gets freshly reloaded per-request via Flask-Login's
# user_loader and needs a consistently-behaving session to do that.

def test_get_queue_returns_pending_items_sorted_by_score(client, auth, test_user, db_session):
    auth.login()
    db_session.add_all([
        SuggestionQueueItem(user_id=test_user.id, item_type='activity', source_id=1,
                             title='Low', score=0.2, status='pending'),
        SuggestionQueueItem(user_id=test_user.id, item_type='activity', source_id=2,
                             title='High', score=0.9, status='pending'),
        SuggestionQueueItem(user_id=test_user.id, item_type='activity', source_id=3,
                             title='Dismissed', score=0.95, status='dismissed'),
    ])
    db_session.commit()

    response = client.get('/api/suggestions/queue')
    assert response.status_code == 200
    titles = [item['title'] for item in response.get_json()['items']]
    assert titles == ['High', 'Low']  # dismissed excluded, sorted by score desc


def test_dismiss_sets_status(client, auth, test_user, db_session):
    auth.login()
    item = SuggestionQueueItem(user_id=test_user.id, item_type='activity', source_id=1,
                                title='Test', score=0.5, status='pending')
    db_session.add(item)
    db_session.commit()

    response = client.post(f'/api/suggestions/queue/{item.id}/dismiss')
    assert response.status_code == 200
    assert response.get_json()['item']['status'] == 'dismissed'


def test_snooze_defaults_to_24_hours_when_no_body_given(client, auth, test_user, db_session):
    auth.login()
    item = SuggestionQueueItem(user_id=test_user.id, item_type='activity', source_id=1,
                                title='Test', score=0.5, status='pending')
    db_session.add(item)
    db_session.commit()

    with freeze_time('2026-07-30 09:00:00'):
        response = client.post(f'/api/suggestions/queue/{item.id}/snooze')

    assert response.status_code == 200
    data = response.get_json()['item']
    assert data['status'] == 'snoozed'
    assert data['snoozed_until'] == '2026-07-31T09:00:00'


def test_snooze_accepts_explicit_until(client, auth, test_user, db_session):
    auth.login()
    item = SuggestionQueueItem(user_id=test_user.id, item_type='activity', source_id=1,
                                title='Test', score=0.5, status='pending')
    db_session.add(item)
    db_session.commit()

    response = client.post(f'/api/suggestions/queue/{item.id}/snooze', json={'until': '2026-08-15T00:00:00'})
    assert response.status_code == 200
    assert response.get_json()['item']['snoozed_until'] == '2026-08-15T00:00:00'


def test_snooze_rejects_invalid_until(client, auth, test_user, db_session):
    auth.login()
    item = SuggestionQueueItem(user_id=test_user.id, item_type='activity', source_id=1,
                                title='Test', score=0.5, status='pending')
    db_session.add(item)
    db_session.commit()

    response = client.post(f'/api/suggestions/queue/{item.id}/snooze', json={'until': 'not-a-date'})
    assert response.status_code == 400


def test_complete_sets_status_done(client, auth, test_user, db_session):
    auth.login()
    item = SuggestionQueueItem(user_id=test_user.id, item_type='event', source_id=1,
                                title='Test', score=0.5, status='pending')
    db_session.add(item)
    db_session.commit()

    response = client.post(f'/api/suggestions/queue/{item.id}/complete')
    assert response.status_code == 200
    assert response.get_json()['item']['status'] == 'done'


def test_complete_activity_item_also_completes_the_activity(client, auth, test_user, db_session):
    auth.login()
    activity = Activity(title='Test Activity', scheduled_time=datetime(2026, 7, 30, 9, 0, 0),
                         status='upcoming', user_id=test_user.id)
    db_session.add(activity)
    db_session.commit()

    item = SuggestionQueueItem(user_id=test_user.id, item_type='activity', source_id=activity.id,
                                title='Test Activity', score=0.5, status='pending')
    db_session.add(item)
    db_session.commit()
    activity_id = activity.id

    client.post(f'/api/suggestions/queue/{item.id}/complete')

    activity = Activity.query.get(activity_id)
    assert activity.status == 'completed'


def test_actions_404_for_another_users_item(client, auth, test_user, db_session):
    other_user = _create_other_user(db_session)
    item = SuggestionQueueItem(user_id=other_user.id, item_type='activity', source_id=1,
                                title='Not Yours', score=0.5, status='pending')
    db_session.add(item)
    db_session.commit()
    item_id = item.id

    auth.login()
    assert client.post(f'/api/suggestions/queue/{item_id}/dismiss').status_code == 404
    assert client.post(f'/api/suggestions/queue/{item_id}/snooze').status_code == 404
    assert client.post(f'/api/suggestions/queue/{item_id}/complete').status_code == 404


# ---- background job ----
#
# refresh_suggestion_queue pushes its own app context internally (it has to,
# to run standalone under APScheduler with no ambient request/app context).
# When that internal context tears down at the end of the call, Flask-
# SQLAlchemy's teardown hook calls db.session.remove(), detaching any live
# ORM objects a test fetched beforehand -- so these capture plain ids
# upfront and never touch a live User/Activity reference after the call,
# same fix already applied to the calendar background-job tests earlier.

def test_refresh_suggestion_queue_runs_for_all_users(app, test_user, db_session):
    other_user = _create_other_user(db_session)
    now = datetime(2026, 7, 30, 9, 0, 0)

    for user in (test_user, other_user):
        db_session.add(Activity(title=f'Activity for {user.username}', scheduled_time=now + timedelta(hours=2),
                                 status='upcoming', user_id=user.id))
    db_session.commit()
    test_user_id = test_user.id
    other_user_id = other_user.id

    with freeze_time(now):
        refresh_suggestion_queue(app)

    assert SuggestionQueueItem.query.filter_by(user_id=test_user_id).count() > 0
    assert SuggestionQueueItem.query.filter_by(user_id=other_user_id).count() > 0


def test_refresh_suggestion_queue_one_users_failure_does_not_block_others(app, test_user, db_session):
    """Asserts on control flow only -- that the loop still attempts a second
    user after the first raises -- via a call counter that never reads any
    attribute off the `user` argument itself. refresh_suggestion_queue's own
    except-block rollback (a real, necessary recovery step so the loop can
    continue at all) expires every User object the session was already
    tracking, including whichever user is queued up next in this same
    User.query.all() -- touching that second user's .id here would be
    testing an artifact of this test's shared transaction, not the
    try/except behavior this test actually cares about. Success-path
    behavior (rows really get created) is already covered by
    test_refresh_queue_creates_items_from_candidates and
    test_refresh_suggestion_queue_runs_for_all_users; this test's only job
    is the error-isolation property of the per-user try/except itself."""
    _create_other_user(db_session)
    call_count = 0

    def flaky_refresh(user, now=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception('simulated failure')

    with patch('app.tasks.background_tasks.refresh_queue_for_user', side_effect=flaky_refresh):
        refresh_suggestion_queue(app)

    assert call_count == 2
