from ..utils.config import config
from ..utils.logging_setup import get_logger
from .background_tasks import update_activity_importance, update_event_cache

logger = get_logger('scheduler')

def init_scheduler(app, scheduler):
    """Initialize and start the scheduler with all background tasks"""
    if not config.is_main_werkzeug_process():
        return

    with app.app_context():
        # Add jobs
        scheduler.add_job(
            update_activity_importance,
            'interval',
            hours=config.TASK_UPDATE_INTERVAL,
            args=[app]
        )

        scheduler.add_job(
            update_event_cache,
            'interval',
            hours=6,  # Update cache every 6 hours
            args=[app]
        )

        # Start scheduler if not already running
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started with background tasks") 