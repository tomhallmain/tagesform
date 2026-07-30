import pytest
from datetime import datetime, timedelta

from app.models import Activity, Entity, db
from app.services.suggestion_queue_service import (
    _activity_candidates, _entity_candidates, _favorite_categories, _is_entity_open,
    gather_candidates_for_user,
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
