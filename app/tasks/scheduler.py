from ..utils.backup_config import backup_config
from ..utils.config import config
from ..utils.logging_setup import get_logger
from .background_tasks import (
    update_activity_importance, update_event_cache, create_database_backup,
    backfill_computed_calendar_events, refresh_suggestion_queue,
)

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
            hours=config.EVENT_CACHE_UPDATE_INTERVAL,
            args=[app],
        )

        # Run immediately so a newly-added computed calendar source (Hebrew,
        # eventually Coptic) has events cached right away rather than waiting
        # a full interval -- in steady state this job is a no-op regardless.
        scheduler.add_job(
            backfill_computed_calendar_events,
            'interval',
            hours=config.COMPUTED_CALENDAR_BACKFILL_INTERVAL,
            args=[app],
            next_run_time='2025-01-01 00:00:00'
        )

        # Run immediately so the dashboard's suggestion queue isn't empty
        # while waiting for the first scheduled interval.
        scheduler.add_job(
            refresh_suggestion_queue,
            'interval',
            hours=config.SUGGESTION_QUEUE_REFRESH_INTERVAL,
            args=[app],
            next_run_time='2025-01-01 00:00:00'
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