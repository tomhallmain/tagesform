from ..utils.backup_config import backup_config
from ..utils.config import config
from ..utils.logging_setup import get_logger
from .background_tasks import (
    update_activity_importance, update_event_cache, create_database_backup,
    backfill_computed_calendar_events, refresh_suggestion_queue,
    refresh_mustermeister_tasks, refresh_briefkorb_messages,
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

        # Run immediately on every startup -- both jobs are no-ops when
        # unconfigured (see their docstrings), and since this app doesn't
        # run 24/7, an immediate run on each start is this codebase's
        # existing answer to "catch up after however long we were down"
        # rather than waiting out a possibly-missed interval boundary.
        scheduler.add_job(
            refresh_mustermeister_tasks,
            'interval',
            hours=config.MUSTERMEISTER_POLL_INTERVAL,
            args=[app],
            next_run_time='2025-01-01 00:00:00'
        )

        scheduler.add_job(
            refresh_briefkorb_messages,
            'interval',
            hours=config.BRIEFKORB_POLL_INTERVAL,
            args=[app],
            next_run_time='2025-01-01 00:00:00'
        )

        # Run immediately so the dashboard's suggestion queue isn't empty
        # while waiting for the first scheduled interval. This also means
        # the queue refresh (and the planning agent it now also drives, see
        # suggestion_queue_service._plan_candidates) always runs once as
        # soon as the app is next opened, regardless of how long it was
        # down beforehand -- same reasoning as the two jobs above.
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