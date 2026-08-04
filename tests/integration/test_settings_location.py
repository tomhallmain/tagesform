import pytest
from unittest.mock import patch

from app.routes import settings as settings_routes
from app.services.geocoding_service import GeocodeResult

pytestmark = pytest.mark.integration

FAKE_RESULT = GeocodeResult(latitude=61.2, longitude=-149.9, matched_place_id=1)


def test_update_location_geocodes_and_saves(client, auth, test_user, db_session):
    auth.login()
    with patch.object(settings_routes.geocoding_service, 'geocode', return_value=FAKE_RESULT):
        response = client.post('/settings/update-location', data={
            'location': 'Anchorage, AK', 'nearby_distance_miles': '15',
        })
    assert response.status_code == 302

    assert test_user.location == 'Anchorage, AK'
    assert test_user.latitude == pytest.approx(61.2)
    assert test_user.longitude == pytest.approx(-149.9)
    assert test_user.preferences.get('nearby_distance_miles') == 15.0


def test_update_location_saves_text_even_when_unmatched(client, auth, test_user, db_session):
    """The user shouldn't lose what they typed just because it didn't
    resolve -- they can revise it, or see it in the location-issues-style
    signal on their own places."""
    auth.login()
    with patch.object(settings_routes.geocoding_service, 'geocode', return_value=None):
        response = client.post('/settings/update-location', data={'location': 'Zzznotarealplace'})
    assert response.status_code == 302

    assert test_user.location == 'Zzznotarealplace'
    assert test_user.latitude is None


def test_update_location_ignores_invalid_nearby_distance(client, auth, test_user, db_session):
    auth.login()
    test_user.update_preferences({'nearby_distance_miles': 30})

    with patch.object(settings_routes.geocoding_service, 'geocode', return_value=None):
        response = client.post('/settings/update-location', data={
            'location': '', 'nearby_distance_miles': 'not-a-number',
        })
    assert response.status_code == 302

    # invalid value is ignored -- previous preference untouched
    assert test_user.preferences.get('nearby_distance_miles') == 30
