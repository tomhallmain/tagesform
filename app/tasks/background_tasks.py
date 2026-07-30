from datetime import datetime
from ..models import Activity, EventCache, UserCalendarDescriptor, db
from ..services.activity_service import infer_activity_importance
from ..services.integration_service import integration_service
from ..services.custom_calendar_service import (
    parse_descriptor, regenerate_event_cache_for_user, DescriptorValidationError
)
from ..utils.logging_setup import get_logger
from ..services.backup_service import get_backup_service

logger = get_logger('background_tasks')

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
                # scopes this to the global/public rows only, leaving any
                # per-user custom calendar rows (refreshed separately below)
                # untouched.
                EventCache.query.filter_by(year=year, user_id=None).delete()

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
