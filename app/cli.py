"""Flask CLI commands for the gazetteer/geolocation groundwork -- see
docs/entity-geolocation.md. Registered onto the app in create_app().
"""
import os

import click

from .models import Entity, GazetteerPlace, User, db
from .services import geocoding_service
from .utils.logging_setup import get_logger

logger = get_logger('cli')

DEFAULT_GAZETTEER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'gazetteer', 'cities500.tsv'
)
COMMIT_BATCH_SIZE = 2000


@click.command('gazetteer-load')
@click.option('--path', default=DEFAULT_GAZETTEER_PATH, show_default=True,
              help='Tab-separated file: geonameid, asciiname, latitude, longitude, feature_code, '
                   'country_code, admin1_code, population (see data/gazetteer/README.md).')
def gazetteer_load_command(path):
    """Load (or refresh) GazetteerPlace from a bundled GeoNames-format export."""
    if not os.path.exists(path):
        click.echo(f'No such file: {path}')
        return

    loaded = 0
    skipped = 0
    with open(path, encoding='utf-8') as f:
        for line_number, line in enumerate(f, start=1):
            line = line.rstrip('\n')
            if not line:
                continue
            fields = line.split('\t')
            if len(fields) != 8:
                logger.error(f'Skipping malformed gazetteer line {line_number} (expected 8 fields, got {len(fields)})')
                skipped += 1
                continue

            geonameid, asciiname, latitude, longitude, feature_code, country_code, admin1_code, population = fields
            # Parse every field into a local variable before touching the
            # ORM/session at all -- a GazetteerPlace added to the session
            # with only some fields set (e.g. failing on latitude after
            # already being added) sits there half-populated, and the next
            # query's autoflush would try to INSERT it and hit the NOT NULL
            # constraint on latitude/longitude, crashing the whole load on
            # the line *after* the malformed one instead of just skipping it.
            try:
                external_id = int(geonameid)
                parsed_latitude = float(latitude)
                parsed_longitude = float(longitude)
                parsed_population = int(population) if population else None
            except (ValueError, TypeError) as e:
                logger.error(f'Skipping malformed gazetteer line {line_number}: {e}')
                skipped += 1
                continue

            place = GazetteerPlace.query.filter_by(external_id=external_id).first()
            if place is None:
                place = GazetteerPlace(external_id=external_id)
                db.session.add(place)
            place.name = asciiname
            place.normalized_name = asciiname.strip().lower()
            place.latitude = parsed_latitude
            place.longitude = parsed_longitude
            place.feature_type = feature_code or None
            place.country_code = country_code or None
            place.admin_region = admin1_code or None
            place.population = parsed_population

            loaded += 1
            if loaded % COMMIT_BATCH_SIZE == 0:
                db.session.commit()
                click.echo(f'...{loaded} places loaded')

    db.session.commit()
    click.echo(f'Loaded {loaded} places from {path} ({skipped} lines skipped).')


@click.command('geocode-backfill')
def geocode_backfill_command():
    """Geocode existing User/Entity rows that have a location string set but
    no coordinates yet (e.g. rows that predate this feature)."""
    geocoded = 0
    unmatched = 0

    entities = Entity.query.filter(
        Entity.location.isnot(None), Entity.location != '', Entity.latitude.is_(None)
    ).all()
    for entity in entities:
        try:
            result = geocoding_service.geocode(entity.location)
        except Exception as e:
            logger.error(f'Error geocoding entity {entity.id} ({entity.location!r}): {e}')
            continue
        if result is None:
            unmatched += 1
            continue
        entity.latitude = result.latitude
        entity.longitude = result.longitude
        entity.location_matched_place_id = result.matched_place_id
        geocoded += 1

    users = User.query.filter(
        User.location.isnot(None), User.location != '', User.latitude.is_(None)
    ).all()
    for user in users:
        try:
            result = geocoding_service.geocode(user.location)
        except Exception as e:
            logger.error(f'Error geocoding user {user.id} ({user.location!r}): {e}')
            continue
        if result is None:
            unmatched += 1
            continue
        user.latitude = result.latitude
        user.longitude = result.longitude
        user.location_matched_place_id = result.matched_place_id
        geocoded += 1

    db.session.commit()
    click.echo(f'Geocoded {geocoded} rows ({unmatched} location strings did not match the gazetteer).')


def register_cli(app):
    app.cli.add_command(gazetteer_load_command)
    app.cli.add_command(geocode_backfill_command)
