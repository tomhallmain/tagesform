import pytest

from app.cli import gazetteer_load_command, geocode_backfill_command
from app.models import Entity, GazetteerPlace, User
from app.services import geocoding_service
from app.services.geocoding_service import GeocodeResult

pytestmark = pytest.mark.unit

# .callback invokes the plain function Click wraps, bypassing CLI arg
# parsing entirely -- same "call the function under test directly" style
# already used throughout this suite. Called as a plain statement, with no
# `with app.app_context():` wrapper -- unlike update_event_cache (which
# pushes its own nested app context internally, by design, to run
# standalone under APScheduler), neither of these commands pushes one of
# its own; wrapping the call in one anyway pops it again on exit, which
# fires Flask-SQLAlchemy's teardown hook (db.session.remove()) and detaches
# every ORM object touched during the call -- including fixtures created
# earlier in the same test -- breaking any attribute access on them
# afterward. The session-scoped `app` fixture already keeps one ambient
# app context pushed for the whole test session, which is all these need.
_gazetteer_load = gazetteer_load_command.callback
_geocode_backfill = geocode_backfill_command.callback


def _write_tsv(tmp_path, lines):
    path = tmp_path / 'gazetteer.tsv'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return str(path)


# --- gazetteer_load_command ---

def test_gazetteer_load_creates_places_from_valid_tsv(tmp_path, db_session):
    path = _write_tsv(tmp_path, [
        '5879400\tAnchorage\t61.21806\t-149.90028\tPPLA2\tUS\tAK\t289600',
        '2988507\tParis\t48.85341\t2.3488\tPPLC\tFR\t11\t2138551',
    ])
    _gazetteer_load(path)

    assert GazetteerPlace.query.count() == 2
    anchorage = GazetteerPlace.query.filter_by(external_id=5879400).first()
    assert anchorage.name == 'Anchorage'
    assert anchorage.normalized_name == 'anchorage'
    assert anchorage.latitude == pytest.approx(61.21806)
    assert anchorage.longitude == pytest.approx(-149.90028)
    assert anchorage.feature_type == 'PPLA2'
    assert anchorage.country_code == 'US'
    assert anchorage.admin_region == 'AK'
    assert anchorage.population == 289600


def test_gazetteer_load_upserts_existing_place_by_external_id(tmp_path, db_session):
    path = _write_tsv(tmp_path, ['5879400\tAnchorage\t61.21806\t-149.90028\tPPLA2\tUS\tAK\t289600'])
    _gazetteer_load(path)

    # Re-load the same geonameid with an updated population and coordinates.
    path = _write_tsv(tmp_path, ['5879400\tAnchorage\t61.2\t-149.9\tPPLA2\tUS\tAK\t300000'])
    _gazetteer_load(path)

    assert GazetteerPlace.query.count() == 1  # updated in place, not duplicated
    place = GazetteerPlace.query.filter_by(external_id=5879400).first()
    assert place.population == 300000
    assert place.latitude == pytest.approx(61.2)


def test_gazetteer_load_skips_malformed_line_wrong_field_count(tmp_path, db_session):
    path = _write_tsv(tmp_path, [
        '5879400\tAnchorage\t61.21806\t-149.90028\tPPLA2\tUS\tAK\t289600',
        'not\tenough\tfields',
        '2988507\tParis\t48.85341\t2.3488\tPPLC\tFR\t11\t2138551',
    ])
    _gazetteer_load(path)

    # The malformed line is skipped; the valid lines around it still load.
    assert GazetteerPlace.query.count() == 2


def test_gazetteer_load_skips_line_with_non_numeric_latitude(tmp_path, db_session):
    """Regression test: a malformed line used to leave a half-populated
    GazetteerPlace pending in the session (added, but missing the
    NOT NULL latitude/longitude it never got to set), which crashed the
    *next* line's query via autoflush instead of just being skipped."""
    path = _write_tsv(tmp_path, [
        '5879400\tAnchorage\tnot-a-number\t-149.90028\tPPLA2\tUS\tAK\t289600',
        '2988507\tParis\t48.85341\t2.3488\tPPLC\tFR\t11\t2138551',
    ])
    _gazetteer_load(path)  # must not raise

    assert GazetteerPlace.query.count() == 1
    assert GazetteerPlace.query.filter_by(external_id=2988507).first() is not None


def test_gazetteer_load_treats_empty_population_field_as_none(tmp_path, db_session):
    path = _write_tsv(tmp_path, ['5879400\tAnchorage\t61.21806\t-149.90028\tPPLA2\tUS\tAK\t'])
    _gazetteer_load(path)

    place = GazetteerPlace.query.filter_by(external_id=5879400).first()
    assert place.population is None


def test_gazetteer_load_skips_blank_lines(tmp_path, db_session):
    path = _write_tsv(tmp_path, [
        '5879400\tAnchorage\t61.21806\t-149.90028\tPPLA2\tUS\tAK\t289600',
        '',
        '2988507\tParis\t48.85341\t2.3488\tPPLC\tFR\t11\t2138551',
    ])
    _gazetteer_load(path)

    assert GazetteerPlace.query.count() == 2


def test_gazetteer_load_reports_missing_file_without_crashing(tmp_path, db_session):
    missing_path = str(tmp_path / 'does-not-exist.tsv')
    _gazetteer_load(missing_path)  # must not raise

    assert GazetteerPlace.query.count() == 0


# --- geocode_backfill_command ---

@pytest.fixture
def unmatched_entity(test_user, db_session):
    entity = Entity(name='Needs Coords', category='restaurant', user_id=test_user.id,
                     location='Anchorage, AK', latitude=None, longitude=None)
    db_session.add(entity)
    db_session.commit()
    return entity


@pytest.fixture
def already_geocoded_entity(test_user, db_session):
    entity = Entity(name='Already Placed', category='restaurant', user_id=test_user.id,
                     location='Somewhere', latitude=10.0, longitude=20.0)
    db_session.add(entity)
    db_session.commit()
    return entity


def test_geocode_backfill_geocodes_entity_and_user_missing_coordinates(test_user, unmatched_entity, db_session, monkeypatch):
    test_user.location = 'Anchorage, AK'
    test_user.latitude = None
    db_session.commit()

    fake_result = GeocodeResult(latitude=61.2, longitude=-149.9, matched_place_id=42)
    monkeypatch.setattr(geocoding_service, 'geocode', lambda location: fake_result)
    _geocode_backfill()

    entity = Entity.query.get(unmatched_entity.id)
    assert entity.latitude == pytest.approx(61.2)
    assert entity.longitude == pytest.approx(-149.9)
    assert entity.location_matched_place_id == 42

    user = User.query.get(test_user.id)
    assert user.latitude == pytest.approx(61.2)
    assert user.location_matched_place_id == 42


def test_geocode_backfill_skips_rows_that_already_have_coordinates(already_geocoded_entity, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr(geocoding_service, 'geocode', lambda location: calls.append(location))

    _geocode_backfill()

    assert calls == []  # geocode() never called for a row that already has coordinates
    entity = Entity.query.get(already_geocoded_entity.id)
    assert entity.latitude == pytest.approx(10.0)  # untouched
    assert entity.longitude == pytest.approx(20.0)


def test_geocode_backfill_leaves_unmatched_rows_with_null_coordinates(unmatched_entity, db_session, monkeypatch):
    monkeypatch.setattr(geocoding_service, 'geocode', lambda location: None)

    _geocode_backfill()  # must not raise

    entity = Entity.query.get(unmatched_entity.id)
    assert entity.latitude is None
    assert entity.location_matched_place_id is None


def test_geocode_backfill_continues_after_one_rows_geocode_exception(test_user, unmatched_entity, db_session, monkeypatch):
    """No db.session.rollback() call exists anywhere in geocode_backfill_command
    -- a per-row geocode() exception is just caught and logged, so this
    doesn't hit the mid-loop-rollback-expires-other-objects class of issue
    background_tasks.py's loops have to guard against."""
    test_user.location = 'Broken Location'
    test_user.latitude = None
    db_session.commit()
    fake_result = GeocodeResult(latitude=61.2, longitude=-149.9, matched_place_id=42)

    def flaky_geocode(location):
        if location == 'Broken Location':
            raise RuntimeError('boom')
        return fake_result

    monkeypatch.setattr(geocoding_service, 'geocode', flaky_geocode)
    _geocode_backfill()  # must not raise

    entity = Entity.query.get(unmatched_entity.id)
    assert entity.latitude == pytest.approx(61.2)  # still geocoded despite the user's failure

    user = User.query.get(test_user.id)
    assert user.latitude is None  # the row whose geocode() call raised stays ungeocoded


def test_geocode_backfill_ignores_rows_with_no_location_set(test_user, db_session, monkeypatch):
    entity = Entity(name='No Location', category='restaurant', user_id=test_user.id,
                     location=None, latitude=None, longitude=None)
    db_session.add(entity)
    db_session.commit()
    calls = []
    monkeypatch.setattr(geocoding_service, 'geocode', lambda location: calls.append(location))

    _geocode_backfill()

    assert calls == []
