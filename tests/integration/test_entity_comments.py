import pytest
from app.models import Entity, EntityComment, User

from helpers import assert_in_response, assert_not_in_response, expected_text

pytestmark = pytest.mark.integration


def _create_other_user(db_session, username='other_user', email='other@example.com'):
    user = User(username=username, email=email)
    user.set_password('password')
    db_session.add(user)
    db_session.commit()
    return user


def test_get_comment_returns_none_when_no_comment_exists(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.get(f'/api/entities/{place.id}/comment')
    assert response.status_code == 200
    assert response.get_json() == {'comment': None}


def test_get_comment_404s_for_nonexistent_entity(client, auth):
    auth.login()
    response = client.get('/api/entities/999999/comment')
    assert response.status_code == 404


def test_save_comment_creates_new_comment(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.put(f'/api/entities/{place.id}/comment', json={'body': 'Great tacos, go on Tuesdays.'})
    assert response.status_code == 200
    data = response.get_json()
    assert data['comment']['body'] == 'Great tacos, go on Tuesdays.'

    stored = EntityComment.query.filter_by(entity_id=place.id, user_id=test_user.id).first()
    assert stored is not None
    assert stored.body == 'Great tacos, go on Tuesdays.'


def test_save_comment_updates_existing_comment_in_place(client, auth, test_user, db_session):
    """Saving twice must upsert -- one row per (entity, user), not a new row each time."""
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    client.put(f'/api/entities/{place.id}/comment', json={'body': 'First note'})
    response = client.put(f'/api/entities/{place.id}/comment', json={'body': 'Updated note'})
    assert response.status_code == 200
    assert response.get_json()['comment']['body'] == 'Updated note'

    all_comments = EntityComment.query.filter_by(entity_id=place.id, user_id=test_user.id).all()
    assert len(all_comments) == 1
    assert all_comments[0].body == 'Updated note'


def test_save_comment_rejects_empty_body(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.put(f'/api/entities/{place.id}/comment', json={'body': '   '})
    assert response.status_code == 400
    assert response.get_json()['error'] == expected_text('Comment cannot be empty.')
    assert EntityComment.query.filter_by(entity_id=place.id, user_id=test_user.id).first() is None


def test_delete_comment_removes_it(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    client.put(f'/api/entities/{place.id}/comment', json={'body': 'Note to delete'})
    response = client.delete(f'/api/entities/{place.id}/comment')
    assert response.status_code == 200
    assert response.get_json() == {'success': True}
    assert EntityComment.query.filter_by(entity_id=place.id, user_id=test_user.id).first() is None

    get_response = client.get(f'/api/entities/{place.id}/comment')
    assert get_response.get_json() == {'comment': None}


def test_delete_comment_when_none_exists_is_a_no_op(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.delete(f'/api/entities/{place.id}/comment')
    assert response.status_code == 200
    assert response.get_json() == {'success': True}


def test_comment_is_private_to_each_user_on_a_shared_public_place(client, auth, test_user, db_session):
    """Two different users each leaving a note on the same public place must not
    see or clobber each other's note -- and the owner has no visibility into
    another user's note on their own place either."""
    other_user = _create_other_user(db_session)

    place = Entity(name='Popular Cafe', category='cafe', is_public=True, user_id=other_user.id)
    db_session.add(place)
    db_session.commit()

    auth.login()  # logs in as test_user
    client.put(f'/api/entities/{place.id}/comment', json={'body': 'My private note'})

    auth.logout()
    auth.login(username=other_user.username, password='password')

    owner_get = client.get(f'/api/entities/{place.id}/comment')
    assert owner_get.get_json() == {'comment': None}

    client.put(f'/api/entities/{place.id}/comment', json={'body': "Owner's own note"})

    comments = EntityComment.query.filter_by(entity_id=place.id).all()
    assert len(comments) == 2
    bodies_by_user = {c.user_id: c.body for c in comments}
    assert bodies_by_user[test_user.id] == 'My private note'
    assert bodies_by_user[other_user.id] == "Owner's own note"


def test_comment_requires_view_access_to_entity(client, auth, test_user, db_session):
    """A private place not owned by, or shared with, the current user must not
    be commentable -- 403, not a silently created orphaned comment."""
    other_user = _create_other_user(db_session)
    place = Entity(name='Private Place', category='restaurant', is_public=False, user_id=other_user.id)
    db_session.add(place)
    db_session.commit()

    auth.login()
    get_response = client.get(f'/api/entities/{place.id}/comment')
    assert get_response.status_code == 403

    put_response = client.put(f'/api/entities/{place.id}/comment', json={'body': 'Should not be allowed'})
    assert put_response.status_code == 403

    assert EntityComment.query.filter_by(entity_id=place.id).first() is None


def test_comment_allowed_when_entity_shared_with_user(client, auth, test_user, db_session):
    other_user = _create_other_user(db_session)
    place = Entity(name='Shared Place', category='restaurant', is_public=False,
                    shared_with=[test_user.id], user_id=other_user.id)
    db_session.add(place)
    db_session.commit()

    auth.login()
    response = client.put(f'/api/entities/{place.id}/comment', json={'body': 'Thanks for sharing'})
    assert response.status_code == 200


def test_places_page_reflects_comment_state_in_icon(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Test Place', category='restaurant', user_id=test_user.id)
    db_session.add(place)
    db_session.commit()

    response = client.get('/places')
    assert response.status_code == 200
    assert_in_response(f'data-entity-id="{place.id}"', response)
    assert_not_in_response('fas fa-sticky-note', response)

    client.put(f'/api/entities/{place.id}/comment', json={'body': 'Nice spot'})

    response = client.get('/places')
    assert_in_response('fas fa-sticky-note', response)
