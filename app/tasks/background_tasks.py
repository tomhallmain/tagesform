from datetime import datetime
from ..models import (
    Activity, BriefKorbMessageCache, DefaultEventDescriptor, Entity, EventCache,
    MustermeisterTaskCache, User, UserCalendarDescriptor, db,
)
from ..services.activity_service import infer_activity_importance
from ..services.integration_service import integration_service
from ..services.calendar_aggregator import format_event
from ..services.custom_calendar_service import (
    parse_descriptor, regenerate_event_cache_for_user, DescriptorValidationError
)
from ..services.entity_calendar_service import regenerate_event_cache_for_entity
from ..services.default_event_service import regenerate_event_cache_for_user_default_events
from ..services import briefkorb_client, mustermeister_client
from ..services.suggestion_queue_service import refresh_queue_for_user
from ..utils.config import config
from ..utils.logging_setup import get_logger
from ..services.backup_service import get_backup_service

logger = get_logger('background_tasks')

# How many years ahead to keep backfilled for computed/deterministic calendar
# sources (see backfill_computed_calendar_events). Wide enough that opening
# the dashboard's "This Year"/"Next Year" view never needs a live fetch.
COMPUTED_CALENDAR_BACKFILL_YEARS = 10


def _computed_calendar_sources():
    """Source-name -> API client mapping for calendar sources that are
    computed/deterministic (fixed calendar rules) rather than live-changing
    -- refreshed only by backfill_computed_calendar_events's long-horizon
    cadence, never by update_event_cache's short cycle. Shared between both
    jobs so update_event_cache's per-year cache refresh can exclude these
    rows by name -- without that, its blanket delete-and-reinsert would wipe
    them out on every run and never put them back, since
    fetch_live_calendar_events doesn't return them.
    """
    return {
        'Hebcal': integration_service.calendar_aggregator.hebcal_api,
        'USNO': integration_service.calendar_aggregator.usno_astronomical_events_api,
        'Nobel Prize': integration_service.calendar_aggregator.nobel_prize_schedule,
        'Inadiutorium API': integration_service.calendar_aggregator.inadiutorium_api,
    }

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
                # Also excludes computed-calendar sources (Hebcal/USNO/Nobel
                # Prize/Inadiutorium) -- those are refreshed only by
                # backfill_computed_calendar_events, and fetch_live_calendar_events
                # never returns them, so deleting them here would wipe them
                # out until the next backfill run without ever reinserting
                # them.
                EventCache.query.filter_by(year=year, user_id=None, entity_id=None) \
                    .filter(EventCache.source.notin_(list(_computed_calendar_sources().keys()))) \
                    .delete(synchronize_session=False)

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

        # Refresh each user's subscribed Default Events (the app-wide
        # catalog, e.g. Kentucky Derby) independently -- same reasoning as
        # the two loops above. Skipped entirely for a user with no
        # subscriptions, so this is a no-op until someone opts into
        # anything on the settings page.
        #
        # Reads (id, subscribed_ids) into plain tuples up front, before the
        # loop runs, rather than keeping the User ORM objects themselves and
        # reading .preferences per-iteration -- db.session.rollback() in the
        # except branch below expires every object still tracked by the
        # session, not just the one that failed, so a later iteration's
        # user.preferences access would otherwise force an implicit reload
        # of an already-expired instance. Plain tuples sidestep that
        # entirely, since nothing after this point touches a User attribute.
        if DefaultEventDescriptor.query.count():
            users_with_subscriptions = [
                (user.id, (user.preferences or {}).get('subscribed_default_events') or [])
                for user in User.query.all()
            ]
            for user_id, subscribed_ids in users_with_subscriptions:
                if not subscribed_ids:
                    continue
                try:
                    regenerate_event_cache_for_user_default_events(
                        user_id, subscribed_ids, years=[current_year, current_year + 1]
                    )
                except Exception as e:
                    logger.error(f"Error refreshing default events for user {user_id}: {e}")
                    db.session.rollback()

def backfill_computed_calendar_events(app):
    """Background job to backfill computed/deterministic calendar sources
    (Hebrew via Hebcal; equinoxes/solstices/eclipses/moon phases via USNO;
    the curated Nobel Prize schedule; the Roman Catholic liturgical calendar
    via Inadiutorium; Coptic, once added) a wide horizon ahead.

    Unlike update_event_cache's sources (Nager, Hijri, Launch Library),
    these calendars' dates never change once computed -- there's nothing to
    "refresh." This job just tops up EventCache so a rolling
    COMPUTED_CALENDAR_BACKFILL_YEARS window is always covered; in steady
    state it finds every year already cached and does nothing. Real work
    happens once (an effective one-time backfill) and roughly once a year
    after that, to extend the tail.
    """
    with app.app_context():
        current_year = datetime.now().year
        target_years = set(range(current_year, current_year + COMPUTED_CALENDAR_BACKFILL_YEARS))

        for source_name, api in _computed_calendar_sources().items():
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

def refresh_mustermeister_tasks(app):
    """Background job to poll Mustermeister's task-insights API and refresh
    MustermeisterTaskCache. The suggestion queue's _task_candidates reads
    only this local cache, never Mustermeister live, same split as
    EventCache/get_calendar_events.

    Upserts by external_id; deletes cached rows Mustermeister no longer
    returns (task completed/deleted/reassigned upstream) -- the fetched set
    is already "every open task," so anything missing from it no longer
    qualifies.

    A no-op (not an error) while MUSTERMEISTER_BASE_URL/API_TOKEN are unset --
    this job is registered unconditionally, but the integration itself is
    opt-in per deployment, so an unconfigured install shouldn't accumulate
    an error-level log line every poll interval forever.
    """
    if not config.MUSTERMEISTER_BASE_URL or not config.MUSTERMEISTER_API_TOKEN:
        logger.warning("Mustermeister integration not configured; skipping poll")
        return

    with app.app_context():
        try:
            tasks = mustermeister_client.fetch_open_tasks()
        except Exception as e:
            logger.error(f"Error fetching Mustermeister tasks: {e}")
            return

        try:
            seen_external_ids = set()
            for task in tasks:
                seen_external_ids.add(task['external_id'])
                cached = MustermeisterTaskCache.query.filter_by(external_id=task['external_id']).first()
                if cached is None:
                    cached = MustermeisterTaskCache(external_id=task['external_id'])
                    db.session.add(cached)
                cached.title = task['title']
                cached.description = task['description']
                cached.due_date = task['due_date']
                cached.completed = task['completed']
                cached.priority = task['priority']
                cached.status = task['status']
                cached.project = task['project']
                cached.updated_date = task['updated_date']
                cached.fetched_at = datetime.utcnow()

            if seen_external_ids:
                MustermeisterTaskCache.query.filter(
                    MustermeisterTaskCache.external_id.notin_(seen_external_ids)
                ).delete(synchronize_session=False)
            else:
                MustermeisterTaskCache.query.delete(synchronize_session=False)

            db.session.commit()
            logger.info(f"Updated Mustermeister task cache with {len(tasks)} open tasks")
        except Exception as e:
            logger.error(f"Error updating Mustermeister task cache: {e}")
            db.session.rollback()


def refresh_briefkorb_messages(app):
    """Background job to poll BriefKorb's messages API and refresh
    BriefKorbMessageCache. The suggestion queue's _email_candidates reads
    only this local cache, never BriefKorb live (every BriefKorb call is a
    live Graph/Gmail fetch against its own quota).

    Upserts by (sender_address, provider); deletes cached buckets BriefKorb
    no longer returns (all read/archived upstream, or dropped since none of
    that sender's messages are unread anymore).

    A no-op (not an error) while BRIEFKORB_BASE_URL/API_TOKEN are unset --
    see refresh_mustermeister_tasks for why.
    """
    if not config.BRIEFKORB_BASE_URL or not config.BRIEFKORB_API_TOKEN:
        logger.warning("BriefKorb integration not configured; skipping poll")
        return

    with app.app_context():
        try:
            buckets = briefkorb_client.fetch_unread_messages()
        except Exception as e:
            logger.error(f"Error fetching BriefKorb messages: {e}")
            return

        try:
            seen_keys = set()
            for bucket in buckets:
                key = (bucket['sender_address'], bucket['provider'])
                seen_keys.add(key)
                cached = BriefKorbMessageCache.query.filter_by(
                    sender_address=bucket['sender_address'], provider=bucket['provider']
                ).first()
                if cached is None:
                    cached = BriefKorbMessageCache(
                        sender_address=bucket['sender_address'], provider=bucket['provider']
                    )
                    db.session.add(cached)
                cached.sender_name = bucket['sender_name']
                cached.subject = bucket['subject']
                cached.last_received_at = bucket['last_received_at']
                cached.count = bucket['count']
                cached.impact = bucket['impact']
                cached.impact_score = bucket['impact_score']
                cached.fetched_at = datetime.utcnow()

            if seen_keys:
                for cached in BriefKorbMessageCache.query.all():
                    if (cached.sender_address, cached.provider) not in seen_keys:
                        db.session.delete(cached)
            else:
                BriefKorbMessageCache.query.delete(synchronize_session=False)

            db.session.commit()
            logger.info(f"Updated BriefKorb message cache with {len(buckets)} unread sender buckets")
        except Exception as e:
            logger.error(f"Error updating BriefKorb message cache: {e}")
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
