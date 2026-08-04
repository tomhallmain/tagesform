import pytest

from app.models import GazetteerPlace
from app.services import geocoding_service
from app.services.geocoding_service import GeocodeResult, apply_geocode, geocode

pytestmark = pytest.mark.unit


def _seed_places(db_session):
    places = [
        GazetteerPlace(external_id=1, name='Anchorage', normalized_name='anchorage',
                        admin_region='AK', country_code='US', population=289600,
                        latitude=61.21806, longitude=-149.90028),
        GazetteerPlace(external_id=2, name='Aku', normalized_name='aku',
                        admin_region='47', country_code='CN', population=1000,
                        latitude=10.0, longitude=100.0),
        GazetteerPlace(external_id=3, name='Springfield', normalized_name='springfield',
                        admin_region='IL', country_code='US', population=114394,
                        latitude=39.8, longitude=-89.6),
        GazetteerPlace(external_id=4, name='Springfield', normalized_name='springfield',
                        admin_region='MO', country_code='US', population=170188,
                        latitude=37.2, longitude=-93.3),
        GazetteerPlace(external_id=5, name='Paris', normalized_name='paris',
                        admin_region='11', country_code='FR', population=2138551,
                        latitude=48.85, longitude=2.35),
        GazetteerPlace(external_id=6, name='Paris', normalized_name='paris',
                        admin_region='TX', country_code='US', population=25000,
                        latitude=33.66, longitude=-95.56),
    ]
    db_session.add_all(places)
    db_session.commit()
    return places


def test_geocode_exact_match(app, db_session):
    with app.app_context():
        _seed_places(db_session)
        result = geocode('Anchorage, AK')

    assert result is not None
    assert result.latitude == pytest.approx(61.21806)
    assert result.longitude == pytest.approx(-149.90028)


def test_geocode_fuzzy_match_tolerates_transposition_typo(app, db_session):
    """The concrete motivating case: a typo'd city name should still
    resolve, not just an exact spelling."""
    with app.app_context():
        _seed_places(db_session)
        result = geocode('Anchoarge, AK')

    assert result is not None
    assert result.latitude == pytest.approx(61.21806)


def test_geocode_short_region_code_is_never_treated_as_a_name_candidate(app, db_session):
    """Regression test: an earlier version of this matcher resolved
    "Anchorage, AK" to a place literally named "Aku" because the region
    segment "AK" itself fuzzy-matched before "Anchorage" was ever tried."""
    with app.app_context():
        _seed_places(db_session)
        result = geocode('Anchorage, AK')

    place = GazetteerPlace.query.filter_by(external_id=1).first()
    assert result.latitude == pytest.approx(place.latitude)
    assert result.longitude == pytest.approx(place.longitude)


def test_geocode_returns_none_for_unmatched_location(app, db_session):
    with app.app_context():
        _seed_places(db_session)
        assert geocode('Zzznotarealplace') is None


def test_geocode_returns_none_for_empty_or_blank_string(app, db_session):
    with app.app_context():
        _seed_places(db_session)
        assert geocode('') is None
        assert geocode('   ') is None
        assert geocode(None) is None


def test_geocode_prefers_region_hint_match_over_population(app, db_session):
    with app.app_context():
        _seed_places(db_session)
        result = geocode('Springfield, IL')

    place = GazetteerPlace.query.filter_by(admin_region='IL', normalized_name='springfield').first()
    assert result.latitude == pytest.approx(place.latitude)


def test_geocode_falls_back_to_population_without_a_region_match(app, db_session):
    """No region hint at all -- among multiple exact-name matches, the
    most populous is the reasonable default guess."""
    with app.app_context():
        _seed_places(db_session)
        result = geocode('Springfield')

    place = GazetteerPlace.query.filter_by(admin_region='MO', normalized_name='springfield').first()
    assert result.latitude == pytest.approx(place.latitude)


def test_geocode_street_address_uses_city_segment_not_region(app, db_session):
    with app.app_context():
        _seed_places(db_session)
        result = geocode('123 Main St, Anchorage, Alaska')

    place = GazetteerPlace.query.filter_by(external_id=1).first()
    assert result.latitude == pytest.approx(place.latitude)


def test_apply_geocode_sets_coordinates_on_match(app, db_session, test_user):
    with app.app_context():
        _seed_places(db_session)
        test_user.location = 'Anchorage, AK'
        apply_geocode(test_user, test_user.location)

    assert test_user.latitude == pytest.approx(61.21806)
    assert test_user.longitude == pytest.approx(-149.90028)
    assert test_user.location_matched_place_id is not None


def test_apply_geocode_clears_coordinates_when_unmatched(app, db_session, test_user):
    with app.app_context():
        _seed_places(db_session)
        test_user.latitude = 1.0
        test_user.longitude = 1.0
        apply_geocode(test_user, 'Zzznotarealplace')

    assert test_user.latitude is None
    assert test_user.longitude is None
    assert test_user.location_matched_place_id is None


def test_apply_geocode_survives_geocode_exception(app, db_session, test_user, monkeypatch):
    """A geocoding failure must never block whatever save apply_geocode is
    part of -- it should leave coordinates null, not raise."""
    def broken_geocode(location):
        raise RuntimeError('boom')

    monkeypatch.setattr(geocoding_service, 'geocode', broken_geocode)
    with app.app_context():
        apply_geocode(test_user, 'Anchorage, AK')  # must not raise

    assert test_user.latitude is None
