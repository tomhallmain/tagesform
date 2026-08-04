import pytest
from unittest.mock import patch

from app.models import Entity, db
from app.routes import entities as entities_routes
from app.services.geocoding_service import GeocodeResult

pytestmark = pytest.mark.integration

FAKE_RESULT = GeocodeResult(latitude=61.2, longitude=-149.9, matched_place_id=1)


def test_add_place_geocodes_location_on_save(client, auth, db_session):
    auth.login()
    with patch.object(entities_routes.geocoding_service, 'geocode', return_value=FAKE_RESULT):
        response = client.post('/add-place', data={
            'name': 'Geocoded Place', 'category': 'restaurant', 'location': 'Anchorage, AK',
        })
    assert response.status_code == 302

    place = Entity.query.filter_by(name='Geocoded Place').first()
    assert place.latitude == pytest.approx(61.2)
    assert place.longitude == pytest.approx(-149.9)
    assert place.location_matched_place_id == 1


def test_add_place_leaves_coordinates_null_when_unmatched(client, auth, db_session):
    auth.login()
    with patch.object(entities_routes.geocoding_service, 'geocode', return_value=None):
        response = client.post('/add-place', data={
            'name': 'Unmatched Place', 'category': 'restaurant', 'location': 'Zzznotarealplace',
        })
    assert response.status_code == 302

    place = Entity.query.filter_by(name='Unmatched Place').first()
    assert place is not None
    assert place.latitude is None


def test_edit_place_regeocodes_when_location_changes(client, auth, test_user, db_session):
    auth.login()
    place = Entity(name='Movable Place', category='restaurant', user_id=test_user.id,
                    location='Old Address', latitude=1.0, longitude=1.0)
    db_session.add(place)
    db_session.commit()

    with patch.object(entities_routes.geocoding_service, 'geocode', return_value=FAKE_RESULT):
        response = client.post(f'/edit-place/{place.id}', data={
            'name': 'Movable Place', 'category': 'restaurant', 'location': 'Anchorage, AK',
        })
    assert response.status_code == 302

    updated = Entity.query.get(place.id)
    assert updated.latitude == pytest.approx(61.2)
    assert updated.longitude == pytest.approx(-149.9)


def test_location_issues_scoped_to_own_entities_only(client, auth, test_user, db_session):
    from app.models import User

    other_user = User(username='other_user2', email='other2@example.com')
    other_user.set_password('password')
    db_session.add(other_user)
    db_session.commit()

    auth.login()
    own_unmatched = Entity(name='My Unmatched Place', category='restaurant', user_id=test_user.id,
                            location='Nowhere Special', latitude=None, longitude=None)
    own_matched = Entity(name='My Matched Place', category='restaurant', user_id=test_user.id,
                          location='Anchorage, AK', latitude=61.2, longitude=-149.9)
    other_unmatched_public = Entity(name='Other Unmatched Public Place', category='restaurant',
                                     user_id=other_user.id, location='Nowhere Else',
                                     latitude=None, longitude=None, is_public=True)
    db_session.add_all([own_unmatched, own_matched, other_unmatched_public])
    db_session.commit()

    response = client.get('/location-issues')
    assert response.status_code == 200
    body = response.get_data(as_text=True)

    assert 'My Unmatched Place' in body
    assert 'My Matched Place' not in body
    # Scoped to the current user's own places -- never another user's,
    # even a public one the current user could otherwise view/edit-check.
    assert 'Other Unmatched Public Place' not in body


def test_places_list_shows_location_issue_count(client, auth, test_user, db_session):
    auth.login()
    db_session.add(Entity(name='Needs Data', category='restaurant', user_id=test_user.id,
                           location='Somewhere Vague', latitude=None, longitude=None))
    db_session.commit()

    response = client.get('/places')
    assert response.status_code == 200
    assert b'could not be matched' in response.data
