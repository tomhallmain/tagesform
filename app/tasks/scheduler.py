from ..utils.backup_config import backup_config
from ..utils.config import config
from ..utils.logging_setup import get_logger
from .background_tasks import update_activity_importance, update_event_cache, create_database_backup

logger = get_logger('scheduler')

def init_scheduler(app, scheduler):
    """Initialize and start the scheduler with all background tasks"""
    if not config.is_main_werkzeug_process():
        return

    with app.app_context():
        # Add jobs with immediate execution and intervals
        scheduler.add_job(
            update_activity_importance,
            'interval',
            hours=config.TASK_UPDATE_INTERVAL,
            args=[app],
        )

        scheduler.add_job(
            update_event_cache,
            'interval',
            hours=3,  # Update cache every 3 hours
            args=[app],
        )

        # Add database backup job with configurable interval
        backup_interval = backup_config.get_backup_interval_hours()
        scheduler.add_job(
            create_database_backup,
            'interval',
            hours=backup_interval,
            args=[app],
            next_run_time='2025-01-01 00:00:00'  # Run immediately
        )

        # Start scheduler if not already running
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started with background tasks") 