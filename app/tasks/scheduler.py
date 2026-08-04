from datetime import datetime

from ..utils.backup_config import backup_config
from ..utils.config import config
from ..utils.logging_setup import get_logger
from .background_tasks import (
    update_activity_importance, update_event_cache, create_database_backup,
    backfill_computed_calendar_events, refresh_suggestion_queue,
    refresh_mustermeister_tasks, refresh_briefkorb_messages,
)

logger = get_logger('scheduler')


def _run_immediately_kwargs():
    """kwargs for scheduler.add_job that make a job fire on this startup,
    however long the app was closed beforehand -- several jobs in this app
    are meant to catch up on startup (this app isn't run 24/7) rather than
    wait out a possibly-long-missed interval.

    A fixed past `next_run_time` (e.g. '2025-01-01 00:00:00') does NOT
    achieve this despite looking like it should -- APScheduler's default
    misfire_grace_time is 1 second, so a next_run_time that's months/years
    in the past is treated as *missed* (logged as a WARNING, silently
    skipped) rather than run, and the job's next fire time is instead
    recomputed to the next regular interval boundary after "now." This is
    exactly the "Run time of job X was missed by Y" warning seen at
    startup. next_run_time must be (approximately) "now," not "any time in
    the past," and misfire_grace_time=None removes the 1-second race
    against however long start-up itself takes between this call and the
    scheduler actually polling for due jobs.
    """
    return {'next_run_time': datetime.now(), 'misfire_grace_time': None}


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
            **_run_immediately_kwargs(),
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
            **_run_immediately_kwargs(),
        )

        scheduler.add_job(
            refresh_briefkorb_messages,
            'interval',
            hours=config.BRIEFKORB_POLL_INTERVAL,
            args=[app],
            **_run_immediately_kwargs(),
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
            **_run_immediately_kwargs(),
        )

        # Add database backup job with configurable interval
        backup_interval = backup_config.get_backup_interval_hours()
        scheduler.add_job(
            create_database_backup,
            'interval',
            hours=backup_interval,
            args=[app],
            **_run_immediately_kwargs(),
        )

        # Start scheduler if not already running
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started with background tasks") 