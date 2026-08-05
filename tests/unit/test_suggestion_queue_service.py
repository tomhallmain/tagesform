import pytest
from datetime import date, datetime, timedelta

from app.models import Activity, BriefKorbMessageCache, Entity, MustermeisterTaskCache, db
from app.services import suggestion_queue_service
from app.services.suggestion_queue_service import (
    _activity_candidates, _email_candidates, _entity_candidates, _favorite_categories,
    _is_entity_open, _task_candidates, gather_candidates_for_user,
)

pytestmark = pytest.mark.unit


def test_favorite_categories_defaults_to_empty_set_when_not_set(test_user):
    assert _favorite_categories(test_user) == set()


def test_favorite_categories_reads_preferences_when_present(test_user):
    """Nothing in settings.py writes this preference today -- checking for
    it anyway means the signal activates automatically if it's ever added,
    without needing to change this scoring code."""
    test_user.preferences = {'favorite_categories': ['restaurant', 'work']}
    assert _favorite_categories(test_user) == {'restaurant', 'work'}


def test_is_entity_open_assumes_open_when_no_hours_set():
    entity = Entity(name='Test', category='restaurant', user_id=1)
    assert _is_entity_open(entity, 'monday', 12) is True


def test_is_entity_open_true_within_hours():
    entity = Entity(name='Test', category='restaurant', user_id=1,
                     operating_hours={'monday': {'open': '09:00', 'close': '17:00'}})
    assert _is_entity_open(entity, 'monday', 12) is True


def test_is_entity_open_false_outside_hours():
    entity = Entity(name='Test', category='restaurant', user_id=1,
                     operating_hours={'monday': {'open': '09:00', 'close': '17:00'}})
    assert _is_entity_open(entity, 'monday', 20) is False


def test_is_entity_open_handles_overnight_hours():
    entity = Entity(name='Late Bar', category='bar', user_id=1,
                     operating_hours={'friday': {'open': '20:00', 'close': '02:00'}})
    assert _is_entity_open(entity, 'friday', 23) is True


def test_activity_candidates_scores_due_today_higher_than_due_later(app, test_user, db_session):
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        due_today = Activity(title='Due Today', scheduled_time=now + timedelta(hours=2),
                              status='upcoming', importance=0.5, user_id=test_user.id)
        due_later = Activity(title='Due Later', scheduled_time=now + timedelta(days=10),
                              status='upcoming', importance=0.5, user_id=test_user.id)
        db_session.add_all([due_today, due_later])
        db_session.commit()

        candidates = _activity_candidates(test_user, now)

        by_title = {c['title']: c for c in candidates}
        assert by_title['Due Today']['score'] > by_title['Due Later']['score']
        assert by_title['Due Today']['item_type'] == 'activity'
        assert by_title['Due Today']['source_id'] == due_today.id


def test_activity_candidates_excludes_completed_and_out_of_window_activities(app, test_user, db_session):
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        completed = Activity(title='Completed', scheduled_time=now + timedelta(hours=2),
                              status='completed', user_id=test_user.id)
        too_far_out = Activity(title='Too Far Out', scheduled_time=now + timedelta(days=30),
                                status='upcoming', user_id=test_user.id)
        db_session.add_all([completed, too_far_out])
        db_session.commit()

        candidates = _activity_candidates(test_user, now)

        titles = {c['title'] for c in candidates}
        assert 'Completed' not in titles
        assert 'Too Far Out' not in titles


def test_activity_candidates_boosts_favorite_category(app, test_user, db_session):
    with app.app_context():
        test_user.preferences = {'favorite_categories': ['health']}
        now = datetime(2026, 7, 30, 9, 0, 0)
        favorite = Activity(title='Gym', scheduled_time=now + timedelta(hours=2), category='health',
                             status='upcoming', importance=0.5, user_id=test_user.id)
        other = Activity(title='Chores', scheduled_time=now + timedelta(hours=2), category='other',
                          status='upcoming', importance=0.5, user_id=test_user.id)
        db_session.add_all([favorite, other])
        db_session.commit()

        candidates = _activity_candidates(test_user, now)
        by_title = {c['title']: c for c in candidates}

        assert by_title['Gym']['score'] > by_title['Chores']['score']


def test_entity_candidates_excludes_poorly_rated_places(app, test_user, db_session):
    with app.app_context():
        poor = Entity(name='Poor Place', category='restaurant', rating=1, user_id=test_user.id)
        good = Entity(name='Good Place', category='restaurant', rating=4, user_id=test_user.id)
        db_session.add_all([poor, good])
        db_session.commit()

        candidates = _entity_candidates(test_user, datetime(2026, 7, 30, 12, 0, 0))
        names = {c['title'] for c in candidates}

        assert 'Poor Place' not in names
        assert 'Good Place' in names


def test_entity_candidates_boosts_unvisited_places(app, test_user, db_session):
    with app.app_context():
        unvisited = Entity(name='New Spot', category='restaurant', rating=3, visited=False, user_id=test_user.id)
        visited = Entity(name='Old Spot', category='restaurant', rating=3, visited=True, user_id=test_user.id)
        db_session.add_all([unvisited, visited])
        db_session.commit()

        candidates = _entity_candidates(test_user, datetime(2026, 7, 30, 12, 0, 0))
        by_title = {c['title']: c for c in candidates}

        assert by_title['New Spot']['score'] > by_title['Old Spot']['score']


def test_entity_candidates_does_not_include_other_users_private_places(app, test_user, db_session):
    from app.models import User
    other_user = User(username='other_user', email='other@example.com')
    other_user.set_password('password')
    db_session.add(other_user)
    db_session.commit()

    with app.app_context():
        private_place = Entity(name='Private Place', category='restaurant', rating=4,
                                is_public=False, user_id=other_user.id)
        db_session.add(private_place)
        db_session.commit()

        candidates = _entity_candidates(test_user, datetime(2026, 7, 30, 12, 0, 0))
        names = {c['title'] for c in candidates}

        assert 'Private Place' not in names


def test_gather_candidates_for_user_combines_activity_and_entity_candidates(app, test_user, db_session):
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        db_session.add(Activity(title='Test Activity', scheduled_time=now + timedelta(hours=2),
                                 status='upcoming', user_id=test_user.id))
        db_session.add(Entity(name='Test Place', category='restaurant', rating=3, user_id=test_user.id))
        db_session.commit()

        candidates = gather_candidates_for_user(test_user, now)
        item_types = {c['item_type'] for c in candidates}

        assert 'activity' in item_types
        assert 'entity' in item_types


def test_task_candidates_empty_when_integration_not_configured_for_user(app, test_user, db_session, monkeypatch):
    monkeypatch.setattr(suggestion_queue_service.config, 'TASK_EMAIL_INTEGRATION_USER_ID', test_user.id + 999)
    with app.app_context():
        db_session.add(MustermeisterTaskCache(external_id=1, title='Some task', priority='high'))
        db_session.commit()

        assert _task_candidates(test_user, datetime(2026, 7, 30, 9, 0, 0)) == []


def test_task_candidates_scores_overdue_higher_than_far_future(app, test_user, db_session, monkeypatch):
    monkeypatch.setattr(suggestion_queue_service.config, 'TASK_EMAIL_INTEGRATION_USER_ID', test_user.id)
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        overdue = MustermeisterTaskCache(external_id=1, title='Overdue', priority='medium',
                                          due_date=date(2026, 7, 28), project='Website', status='In Progress')
        far_future = MustermeisterTaskCache(external_id=2, title='Far Future', priority='medium',
                                             due_date=date(2026, 8, 20))
        db_session.add_all([overdue, far_future])
        db_session.commit()

        candidates = _task_candidates(test_user, now)
        by_title = {c['title']: c for c in candidates}

        assert by_title['Overdue']['score'] > by_title['Far Future']['score']
        assert by_title['Overdue']['item_type'] == 'task'
        assert by_title['Overdue']['source_id'] == overdue.id
        # internal-only fields read by planning_agent_service must survive:
        assert by_title['Overdue']['due_date'] == date(2026, 7, 28)
        assert by_title['Overdue']['priority'] == 'medium'
        assert by_title['Overdue']['project'] == 'Website'
        assert by_title['Overdue']['status'] == 'In Progress'


def test_task_candidates_handles_missing_due_date(app, test_user, db_session, monkeypatch):
    monkeypatch.setattr(suggestion_queue_service.config, 'TASK_EMAIL_INTEGRATION_USER_ID', test_user.id)
    with app.app_context():
        db_session.add(MustermeisterTaskCache(external_id=1, title='No due date', priority='low'))
        db_session.commit()

        candidates = _task_candidates(test_user, datetime(2026, 7, 30, 9, 0, 0))

        assert len(candidates) == 1
        assert candidates[0]['due_date'] is None


def test_email_candidates_empty_when_integration_not_configured_for_user(app, test_user, db_session, monkeypatch):
    monkeypatch.setattr(suggestion_queue_service.config, 'TASK_EMAIL_INTEGRATION_USER_ID', test_user.id + 999)
    with app.app_context():
        db_session.add(BriefKorbMessageCache(sender_address='a@example.com', provider='microsoft',
                                              impact='high-impact', last_received_at=datetime(2026, 7, 30, 8, 0, 0)))
        db_session.commit()

        assert _email_candidates(test_user, datetime(2026, 7, 30, 9, 0, 0)) == []


def test_email_candidates_excludes_low_impact_but_keeps_unclassified(app, test_user, db_session, monkeypatch):
    monkeypatch.setattr(suggestion_queue_service.config, 'TASK_EMAIL_INTEGRATION_USER_ID', test_user.id)
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        low = BriefKorbMessageCache(sender_address='low@example.com', provider='microsoft',
                                     sender_name='Newsletter', impact='low-impact', last_received_at=now)
        unclassified = BriefKorbMessageCache(sender_address='new@example.com', provider='microsoft',
                                              sender_name='New Contact', impact='unclassified',
                                              last_received_at=now)
        db_session.add_all([low, unclassified])
        db_session.commit()

        candidates = _email_candidates(test_user, now)
        senders = {c['sender_name'] for c in candidates}

        assert 'Newsletter' not in senders
        assert 'New Contact' in senders


def test_email_candidates_scores_high_impact_above_unclassified(app, test_user, db_session, monkeypatch):
    monkeypatch.setattr(suggestion_queue_service.config, 'TASK_EMAIL_INTEGRATION_USER_ID', test_user.id)
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        high = BriefKorbMessageCache(sender_address='boss@example.com', provider='microsoft',
                                      sender_name='Boss', impact='high-impact', impact_score=0.9,
                                      last_received_at=now)
        unclassified = BriefKorbMessageCache(sender_address='new@example.com', provider='microsoft',
                                              sender_name='New Contact', impact='unclassified',
                                              impact_score=0.5, last_received_at=now)
        db_session.add_all([high, unclassified])
        db_session.commit()

        candidates = _email_candidates(test_user, now)
        by_sender = {c['sender_name']: c for c in candidates}

        assert by_sender['Boss']['score'] > by_sender['New Contact']['score']
        assert by_sender['Boss']['item_type'] == 'email'
        assert by_sender['Boss']['source_id'] == high.id


def test_gather_candidates_for_user_includes_task_and_email_when_integration_enabled(app, test_user, db_session, monkeypatch):
    monkeypatch.setattr(suggestion_queue_service.config, 'TASK_EMAIL_INTEGRATION_USER_ID', test_user.id)
    monkeypatch.setattr(suggestion_queue_service.config, 'PLANNING_AGENT_ENABLED', False)
    with app.app_context():
        now = datetime(2026, 7, 30, 9, 0, 0)
        db_session.add(MustermeisterTaskCache(external_id=1, title='A task', priority='medium'))
        db_session.add(BriefKorbMessageCache(sender_address='a@example.com', provider='microsoft',
                                              impact='high-impact', last_received_at=now))
        db_session.commit()

        candidates = gather_candidates_for_user(test_user, now)
        item_types = {c['item_type'] for c in candidates}

        assert 'task' in item_types
        assert 'email' in item_types


def test_nearby_distance_miles_defaults_when_no_preference_set(test_user):
    from app.services.suggestion_queue_service import _nearby_distance_miles, DEFAULT_NEARBY_DISTANCE_MILES
    assert _nearby_distance_miles(test_user) == DEFAULT_NEARBY_DISTANCE_MILES


def test_nearby_distance_miles_respects_preference(test_user):
    from app.services.suggestion_queue_service import _nearby_distance_miles
    test_user.preferences = {'nearby_distance_miles': 10}
    assert _nearby_distance_miles(test_user) == 10.0


def test_nearby_distance_miles_falls_back_on_invalid_preference(test_user):
    from app.services.suggestion_queue_service import _nearby_distance_miles, DEFAULT_NEARBY_DISTANCE_MILES
    test_user.preferences = {'nearby_distance_miles': 'not-a-number'}
    assert _nearby_distance_miles(test_user) == DEFAULT_NEARBY_DISTANCE_MILES


def test_entity_candidates_excludes_entities_beyond_nearby_distance(app, test_user, db_session):
    """Anchorage, AK vs Fairbanks, AK -- real-world distance ~260 miles."""
    with app.app_context():
        test_user.latitude = 61.21806
        test_user.longitude = -149.90028
        test_user.preferences = {'nearby_distance_miles': 50}

        near = Entity(name='Near Place', category='restaurant', rating=3, user_id=test_user.id,
                       latitude=61.3, longitude=-149.8)  # a few miles from the user
        far = Entity(name='Far Place', category='restaurant', rating=3, user_id=test_user.id,
                      latitude=64.83778, longitude=-147.71639)  # Fairbanks -- ~260mi away
        db_session.add_all([near, far])
        db_session.commit()

        candidates = _entity_candidates(test_user, datetime(2026, 7, 30, 12, 0, 0))
        names = {c['title'] for c in candidates}

        assert 'Near Place' in names
        assert 'Far Place' not in names


def test_entity_candidates_does_not_exclude_entities_missing_coordinates(app, test_user, db_session):
    """Missing coordinates on either side means 'we don't know', not 'too
    far away' -- must not be excluded on that basis."""
    with app.app_context():
        test_user.latitude = 61.21806
        test_user.longitude = -149.90028
        test_user.preferences = {'nearby_distance_miles': 10}

        no_coords = Entity(name='Ungeocoded Place', category='restaurant', rating=3, user_id=test_user.id)
        db_session.add(no_coords)
        db_session.commit()

        candidates = _entity_candidates(test_user, datetime(2026, 7, 30, 12, 0, 0))
        names = {c['title'] for c in candidates}

        assert 'Ungeocoded Place' in names


def test_entity_candidates_does_not_filter_when_user_has_no_coordinates(app, test_user, db_session):
    with app.app_context():
        test_user.latitude = None
        test_user.longitude = None

        far = Entity(name='Some Place', category='restaurant', rating=3, user_id=test_user.id,
                      latitude=64.83778, longitude=-147.71639)
        db_session.add(far)
        db_session.commit()

        candidates = _entity_candidates(test_user, datetime(2026, 7, 30, 12, 0, 0))
        names = {c['title'] for c in candidates}

        assert 'Some Place' in names
