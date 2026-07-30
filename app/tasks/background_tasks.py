from datetime import datetime
from ..models import Activity, Entity, EventCache, User, UserCalendarDescriptor, db
from ..services.activity_service import infer_activity_importance
from ..services.integration_service import integration_service
from ..services.calendar_aggregator import format_event
from ..services.custom_calendar_service import (
    parse_descriptor, regenerate_event_cache_for_user, DescriptorValidationError
)
from ..services.entity_calendar_service import regenerate_event_cache_for_entity
from ..services.suggestion_queue_service import refresh_queue_for_user
from ..utils.logging_setup import get_logger
from ..services.backup_service import get_backup_service

logger = get_logger('background_tasks')

# How many years ahead to keep backfilled for computed/deterministic calendar
# sources (see backfill_computed_calendar_events). Wide enough that opening
# the dashboard's "This Year"/"Next Year" view never needs a live fetch.
COMPUTED_CALENDAR_BACKFILL_YEARS = 10

def update_activity_importance(app):
    """Background job to update activity importance using LLM inference"""
    with app.app_context():
        try:
            activities = Activity.query.filter_by(status='upcoming').all()
            for activity in activities:
                importance = infer_activity_importance(activity)
                activity.importance = importance
            db.session.commit()
            logger.info(f"Updated importance for {len(activities)} activities")
            
        except Exception as e:
            logger.error(f"Error updating activity importance: {e}")
            db.session.rollback()

def update_event_cache(app):
    """Background job to update the event cache"""
    with app.app_context():
        current_year = datetime.now().year
        try:
            # Get events for current and next year
            for year in [current_year, current_year + 1]:
                # Get fresh events from the live APIs (get_calendar_events reads
                # this cache rather than fetching live -- see integration_service)
                events = integration_service.fetch_live_calendar_events(
                    start_date=datetime(year, 1, 1),
                    end_date=datetime(year, 12, 31)
                )

                # Delete existing global cache for this year -- user_id=None
                # AND entity_id=None scopes this to the global/public rows
                # only. Per-user custom calendar rows and per-entity calendar
                # rows (both refreshed separately below) also have user_id
                # NULL in the entity case, so entity_id=None is required here
                # too, or this would wipe out entity calendar rows every run.
                EventCache.query.filter_by(year=year, user_id=None, entity_id=None).delete()

                # Add new events to cache
                for event_dict in events:
                    cache_entry = EventCache.from_event_dict(event_dict)
                    db.session.add(cache_entry)

                db.session.commit()
                logger.info(f"Updated event cache for year {year}")

        except Exception as e:
            logger.error(f"Error updating event cache: {str(e)}")
            db.session.rollback()

        # Refresh each user's custom calendar independently -- a parse
        # failure for one user's descriptor must not prevent other users'
        # descriptors (or the global cache above) from refreshing.
        for descriptor in UserCalendarDescriptor.query.all():
            try:
                entries = parse_descriptor(descriptor.raw_yaml)
                regenerate_event_cache_for_user(descriptor.user_id, entries, years=[current_year, current_year + 1])
                if descriptor.last_parse_error is not None:
                    descriptor.last_parse_error = None
                    db.session.commit()
            except DescriptorValidationError as e:
                logger.error(f"Error parsing custom calendar for user {descriptor.user_id}: {e}")
                descriptor.last_parse_error = str(e)
                db.session.commit()
            except Exception as e:
                logger.error(f"Error refreshing custom calendar for user {descriptor.user_id}: {e}")
                db.session.rollback()

        # Refresh each entity's calendar independently -- same reasoning as
        # the per-user loop above: one entity's data shouldn't block others.
        entities_with_calendars = Entity.query.filter(Entity.calendar_entries.isnot(None)).all()
        for entity in entities_with_calendars:
            try:
                regenerate_event_cache_for_entity(entity, years=[current_year, current_year + 1])
            except Exception as e:
                logger.error(f"Error refreshing calendar for entity {entity.id}: {e}")
                db.session.rollback()

def backfill_computed_calendar_events(app):
    """Background job to backfill computed/deterministic calendar sources
    (Hebrew via Hebcal; equinoxes/solstices/eclipses/moon phases via USNO;
    the curated Nobel Prize schedule; Coptic, once added) a wide horizon
    ahead.

    Unlike update_event_cache's sources (Nager especially), these calendars'
    dates never change once computed -- there's nothing to "refresh." This
    job just tops up EventCache so a rolling COMPUTED_CALENDAR_BACKFILL_YEARS
    window is always covered; in steady state it finds every year already
    cached and does nothing. Real work happens once (an effective one-time
    backfill) and roughly once a year after that, to extend the tail --
    see docs/hebrew-calendar.md's Caching strategy section.
    """
    with app.app_context():
        current_year = datetime.now().year
        target_years = set(range(current_year, current_year + COMPUTED_CALENDAR_BACKFILL_YEARS))

        computed_sources = {
            'Hebcal': integration_service.calendar_aggregator.hebcal_api,
            'USNO': integration_service.calendar_aggregator.usno_astronomical_events_api,
            'Nobel Prize': integration_service.calendar_aggregator.nobel_prize_schedule,
        }

        for source_name, api in computed_sources.items():
            try:
                existing_years = {
                    row.year for row in
                    EventCache.query.filter_by(source=source_name).with_entities(EventCache.year).distinct()
                }
            except Exception as e:
                logger.error(f"Error checking cached years for {source_name}: {e}")
                continue

            missing_years = sorted(target_years - existing_years)
            for year in missing_years:
                try:
                    events = api.get_events(year)
                    # Defensive: clear any partial rows from a previously
                    # interrupted backfill of this year before reinserting.
                    EventCache.query.filter_by(source=source_name, year=year).delete()
                    for event in events:
                        db.session.add(EventCache.from_event_dict(format_event(event)))
                    db.session.commit()
                    logger.info(f"Backfilled {source_name} events for year {year}")
                except Exception as e:
                    logger.error(f"Error backfilling {source_name} events for year {year}: {e}")
                    db.session.rollback()

def refresh_suggestion_queue(app):
    """Background job to recompute each user's suggestion queue.

    Candidates are drawn from activities, entities, and
    IntegrationService.get_calendar_events (which by now already merges
    public holidays, Hebrew/USNO/Nobel Prize/rocket-launch events, custom
    calendars, and entity calendars -- see suggestion_queue_service.py's
    module docstring). One user's failure must not prevent other users'
    queues from refreshing, same as the per-user/per-entity loops above.
    """
    with app.app_context():
        for user in User.query.all():
            try:
                refresh_queue_for_user(user)
            except Exception as e:
                logger.error(f"Error refreshing suggestion queue for user {user.id}: {e}")
                db.session.rollback()

def create_database_backup(app):
    """Create a database backup"""
    with app.app_context():
        try:
            backup_service = get_backup_service()
            backup_path = backup_service.create_backup()
            if backup_path:
                logger.info(f"Database backup created: {backup_path}")
                
                # Clean up old backups (keep last 10)
                removed_count = backup_service.cleanup_old_backups(keep_count=10)
                if removed_count > 0:
                    logger.info(f"Cleaned up {removed_count} old backups")
            else:
                logger.error("Failed to create database backup")
                
        except Exception as e:
            logger.error(f"Error creating database backup: {str(e)}")
