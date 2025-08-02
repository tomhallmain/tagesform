from datetime import datetime
from ..models import Activity, EventCache, db
from ..services.activity_service import infer_activity_importance
from ..services.integration_service import integration_service
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
        try:
            current_year = datetime.now().year
            # Get events for current and next year
            for year in [current_year, current_year + 1]:
                # Get fresh events from APIs
                events = integration_service.get_calendar_events(
                    start_date=datetime(year, 1, 1),
                    end_date=datetime(year, 12, 31)
                )
                
                # Delete existing cache for this year
                EventCache.query.filter_by(year=year).delete()
                
                # Add new events to cache
                for event_dict in events:
                    cache_entry = EventCache.from_event_dict(event_dict)
                    db.session.add(cache_entry)
                
                db.session.commit()
                logger.info(f"Updated event cache for year {year}")
                
        except Exception as e:
            logger.error(f"Error updating event cache: {str(e)}")
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
