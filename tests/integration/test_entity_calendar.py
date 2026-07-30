import pytest
from datetime import datetime
from unittest.mock import patch
from flask_login import login_user
from freezegun import freeze_time

from app.models import Entity, EventCache, User
from app.services.integration_service import integration_service
from app.tasks.background_tasks import update_event_cache

pytestmark = pytest.mark.integration


def _create_other_user(db_session, username='other_user', email='other@example.com'):
    user = User(username=username, email=email)
    user.set_password('password')
    db_session.add(user)
    db_session.commit()
    return user


def test_create_calendar_entry_requires_ownership(client, auth, test_user, db_session):
    """A user who can merely view a public entity (not own it) must not be
    able to add calendar entries -- matches operating_hours/description edit
    permissions, not EntityComment's (any viewer can write their own
    comment)."""
    other_user = _create_other_user(db_session)
    place = Entity(name='Public Place', category='restaurant', is_public=True, user_id=other_user.id)
    db_session.add(place)
    db_session.commit()

    auth.login()
    response = client.post(f'/api/entities/{place.id}/calendar-entries',
                            json={'title': 'Closed', 'recurrence': 'once', 'date': '2026-12-25'})
    assert response.status_code == 403


def test_create_calendar_entry_success(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    with freeze_time('2026-01-01'):
        response = client.post(f'/api/entities/{place.id}/calendar-entries',
                                json={'title': 'Closed for Christmas', 'entry_type': 'closure',
                                      'recurrence': 'annual', 'month': 12, 'day': 25})

    assert response.status_code == 200
    entry = response.get_json()['entry']
    assert entry['title'] == 'Closed for Christmas'
    assert 'id' in entry and entry['id']

    cached = EventCache.query.filter_by(entity_id=place.id, source='Entity Calendar').all()
    years = {c.year for c in cached}
    assert years == {2026, 2027}


def test_create_calendar_entry_rejects_invalid_input(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.post(f'/api/entities/{place.id}/calendar-entries',
                            json={'recurrence': 'once', 'date': '2026-01-01'})
    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_list_calendar_entries_requires_view_access(client, auth, test_user, db_session):
    other_user = _create_other_user(db_session)
    place = Entity(name='Private Place', category='restaurant', is_public=False, user_id=other_user.id)
    db_session.add(place)
    db_session.commit()

    auth.login()
    response = client.get(f'/api/entities/{place.id}/calendar-entries')
    assert response.status_code == 403


def test_update_calendar_entry(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    create_response = client.post(f'/api/entities/{place.id}/calendar-entries',
                                   json={'title': 'Original', 'recurrence': 'once', 'date': '2026-06-01'})
    entry_id = create_response.get_json()['entry']['id']

    update_response = client.put(f'/api/entities/{place.id}/calendar-entries/{entry_id}',
                                  json={'title': 'Updated', 'recurrence': 'once', 'date': '2026-06-02'})

    assert update_response.status_code == 200
    updated_entry = update_response.get_json()['entry']
    assert updated_entry['title'] == 'Updated'
    assert updated_entry['date'] == '2026-06-02'
    assert updated_entry['id'] == entry_id


def test_update_calendar_entry_not_found(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.put(f'/api/entities/{place.id}/calendar-entries/does-not-exist',
                           json={'title': 'X', 'recurrence': 'once', 'date': '2026-01-01'})
    assert response.status_code == 404


def test_delete_calendar_entry_removes_it_and_its_cache(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    create_response = client.post(f'/api/entities/{place.id}/calendar-entries',
                                   json={'title': 'Closed', 'recurrence': 'once', 'date': '2026-06-01'})
    entry_id = create_response.get_json()['entry']['id']
    assert EventCache.query.filter_by(entity_id=place.id, source='Entity Calendar').count() > 0

    delete_response = client.delete(f'/api/entities/{place.id}/calendar-entries/{entry_id}')
    assert delete_response.status_code == 200

    assert EventCache.query.filter_by(entity_id=place.id, source='Entity Calendar').count() == 0

    list_response = client.get(f'/api/entities/{place.id}/calendar-entries')
    assert list_response.get_json()['entries'] == []


def test_delete_calendar_entry_not_found(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.delete(f'/api/entities/{place.id}/calendar-entries/does-not-exist')
    assert response.status_code == 404


def test_get_calendar_events_includes_owned_entitys_entries(app, test_user, db_session):
    place = Entity(name='My Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    db_session.add(EventCache(title='Closed for Christmas', date=datetime(2026, 12, 25),
                               year=2026, source='Entity Calendar', entity_id=place.id))
    db_session.commit()

    with app.test_request_context():
        login_user(test_user)
        events = integration_service.get_calendar_events(
            start_date=datetime(2026, 12, 1), end_date=datetime(2026, 12, 31)
        )

    assert 'Closed for Christmas' in {e['title'] for e in events}


def test_get_calendar_events_includes_shared_entitys_entries(app, test_user, db_session):
    other_user = _create_other_user(db_session)
    place = Entity(name='Shared Place', category='restaurant', is_public=False,
                    shared_with=[test_user.id], user_id=other_user.id)
    db_session.add(place)
    db_session.commit()

    db_session.add(EventCache(title='Special Hours', date=datetime(2026, 12, 25),
                               year=2026, source='Entity Calendar', entity_id=place.id))
    db_session.commit()

    with app.test_request_context():
        login_user(test_user)
        events = integration_service.get_calendar_events(
            start_date=datetime(2026, 12, 1), end_date=datetime(2026, 12, 31)
        )

    assert 'Special Hours' in {e['title'] for e in events}


def test_get_calendar_events_excludes_public_only_entitys_entries(app, test_user, db_session):
    """A user who can only see an entity because it's public (not owned or
    shared with them) must NOT see its calendar entries -- the recommended
    default from docs/entity-calendar.md's Ownership section, to avoid
    injecting a stranger's business closures into every viewer's personal
    dashboard."""
    other_user = _create_other_user(db_session)
    place = Entity(name='Public Place', category='restaurant', is_public=True, user_id=other_user.id)
    db_session.add(place)
    db_session.commit()

    db_session.add(EventCache(title='Public Place Closure', date=datetime(2026, 12, 25),
                               year=2026, source='Entity Calendar', entity_id=place.id))
    db_session.commit()

    with app.test_request_context():
        login_user(test_user)
        events = integration_service.get_calendar_events(
            start_date=datetime(2026, 12, 1), end_date=datetime(2026, 12, 31)
        )

    assert 'Public Place Closure' not in {e['title'] for e in events}


def test_get_calendar_events_excludes_entitys_entries_with_no_access(app, test_user, db_session):
    other_user = _create_other_user(db_session)
    place = Entity(name='Private Place', category='restaurant', is_public=False, user_id=other_user.id)
    db_session.add(place)
    db_session.commit()

    db_session.add(EventCache(title='Hidden Closure', date=datetime(2026, 12, 25),
                               year=2026, source='Entity Calendar', entity_id=place.id))
    db_session.commit()

    with app.test_request_context():
        login_user(test_user)
        events = integration_service.get_calendar_events(
            start_date=datetime(2026, 12, 1), end_date=datetime(2026, 12, 31)
        )

    assert 'Hidden Closure' not in {e['title'] for e in events}


def test_background_job_refreshes_entity_calendar_annual_entry_into_next_year(app, test_user, db_session):
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    place.add_calendar_entry({
        'id': 'x1', 'title': 'Closed for Christmas', 'entry_type': 'closure',
        'recurrence': 'annual', 'month': 12, 'day': 25, 'date': None, 'description': None,
    })
    place_id = place.id

    with patch.object(integration_service, 'fetch_live_calendar_events', return_value=[]):
        with freeze_time('2027-01-01'):
            update_event_cache(app)

    cached_years = {
        c.year for c in EventCache.query.filter_by(
            entity_id=place_id, source='Entity Calendar', title='Closed for Christmas'
        ).all()
    }
    assert 2028 in cached_years  # rolled forward without the owner re-saving anything


def test_deleting_entity_cleans_up_its_event_cache_rows(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()
    place_id = place.id

    client.post(f'/api/entities/{place_id}/calendar-entries',
                json={'title': 'Closed', 'recurrence': 'once', 'date': '2026-06-01'})
    assert EventCache.query.filter_by(entity_id=place_id, source='Entity Calendar').count() > 0

    client.post(f'/delete-place/{place_id}')

    assert EventCache.query.filter_by(entity_id=place_id, source='Entity Calendar').count() == 0
