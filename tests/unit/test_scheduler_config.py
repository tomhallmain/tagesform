import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.utils.config import Config
from app.tasks import scheduler as scheduler_module

pytestmark = pytest.mark.unit


def test_event_cache_update_interval_defaults_to_24_hours(monkeypatch):
    monkeypatch.delenv('EVENT_CACHE_UPDATE_INTERVAL', raising=False)
    assert Config().EVENT_CACHE_UPDATE_INTERVAL == 24


def test_event_cache_update_interval_respects_env_override(monkeypatch):
    monkeypatch.setenv('EVENT_CACHE_UPDATE_INTERVAL', '6')
    assert Config().EVENT_CACHE_UPDATE_INTERVAL == 6


def test_computed_calendar_backfill_interval_defaults_to_24_hours(monkeypatch):
    monkeypatch.delenv('COMPUTED_CALENDAR_BACKFILL_INTERVAL', raising=False)
    assert Config().COMPUTED_CALENDAR_BACKFILL_INTERVAL == 24


def test_computed_calendar_backfill_interval_respects_env_override(monkeypatch):
    monkeypatch.setenv('COMPUTED_CALENDAR_BACKFILL_INTERVAL', '168')
    assert Config().COMPUTED_CALENDAR_BACKFILL_INTERVAL == 168


def test_init_scheduler_registers_event_cache_job_with_configured_interval(app, monkeypatch):
    """update_event_cache's job must use config.EVENT_CACHE_UPDATE_INTERVAL,
    not a hardcoded value -- this is what makes the interval actually
    configurable via the env var covered above."""
    monkeypatch.setattr(scheduler_module.config, 'is_main_process', True)
    monkeypatch.setattr(scheduler_module.config, 'EVENT_CACHE_UPDATE_INTERVAL', 6)

    mock_scheduler = MagicMock()
    mock_scheduler.running = False

    scheduler_module.init_scheduler(app, mock_scheduler)

    event_cache_call = next(
        call for call in mock_scheduler.add_job.call_args_list
        if call.args[0] is scheduler_module.update_event_cache
    )
    assert event_cache_call.kwargs['hours'] == 6


def test_init_scheduler_registers_computed_calendar_backfill_job_with_configured_interval(app, monkeypatch):
    monkeypatch.setattr(scheduler_module.config, 'is_main_process', True)
    monkeypatch.setattr(scheduler_module.config, 'COMPUTED_CALENDAR_BACKFILL_INTERVAL', 168)

    mock_scheduler = MagicMock()
    mock_scheduler.running = False

    scheduler_module.init_scheduler(app, mock_scheduler)

    backfill_call = next(
        call for call in mock_scheduler.add_job.call_args_list
        if call.args[0] is scheduler_module.backfill_computed_calendar_events
    )
    assert backfill_call.kwargs['hours'] == 168
    # Must run immediately on startup rather than waiting a full interval --
    # otherwise a newly-added computed source shows nothing for up to a week.
    assert 'next_run_time' in backfill_call.kwargs


def test_suggestion_queue_refresh_interval_defaults_to_6_hours(monkeypatch):
    monkeypatch.delenv('SUGGESTION_QUEUE_REFRESH_INTERVAL', raising=False)
    assert Config().SUGGESTION_QUEUE_REFRESH_INTERVAL == 6


def test_suggestion_queue_refresh_interval_respects_env_override(monkeypatch):
    monkeypatch.setenv('SUGGESTION_QUEUE_REFRESH_INTERVAL', '12')
    assert Config().SUGGESTION_QUEUE_REFRESH_INTERVAL == 12


def test_init_scheduler_registers_suggestion_queue_job_with_configured_interval(app, monkeypatch):
    monkeypatch.setattr(scheduler_module.config, 'is_main_process', True)
    monkeypatch.setattr(scheduler_module.config, 'SUGGESTION_QUEUE_REFRESH_INTERVAL', 12)

    mock_scheduler = MagicMock()
    mock_scheduler.running = False

    scheduler_module.init_scheduler(app, mock_scheduler)

    suggestion_call = next(
        call for call in mock_scheduler.add_job.call_args_list
        if call.args[0] is scheduler_module.refresh_suggestion_queue
    )
    assert suggestion_call.kwargs['hours'] == 12
    # Must run immediately so the dashboard isn't empty while waiting for
    # the first scheduled interval.
    assert 'next_run_time' in suggestion_call.kwargs


def test_mustermeister_poll_interval_defaults_to_3_hours(monkeypatch):
    monkeypatch.delenv('MUSTERMEISTER_POLL_INTERVAL', raising=False)
    assert Config().MUSTERMEISTER_POLL_INTERVAL == 3


def test_briefkorb_poll_interval_defaults_to_6_hours(monkeypatch):
    monkeypatch.delenv('BRIEFKORB_POLL_INTERVAL', raising=False)
    assert Config().BRIEFKORB_POLL_INTERVAL == 6


def test_task_email_integration_user_id_defaults_to_none(monkeypatch):
    """Unset by default so the integration is opt-in per deployment --
    see docs/task-email-integration.md."""
    monkeypatch.delenv('TASK_EMAIL_INTEGRATION_USER_ID', raising=False)
    assert Config().TASK_EMAIL_INTEGRATION_USER_ID is None


def test_task_email_integration_user_id_respects_env_override(monkeypatch):
    monkeypatch.setenv('TASK_EMAIL_INTEGRATION_USER_ID', '7')
    assert Config().TASK_EMAIL_INTEGRATION_USER_ID == 7


def test_planning_agent_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv('PLANNING_AGENT_ENABLED', raising=False)
    assert Config().PLANNING_AGENT_ENABLED is False


def test_task_overview_max_per_group_defaults_to_mustermeister_task_limit(monkeypatch):
    """Defaults to the same ceiling as MUSTERMEISTER_TASK_LIMIT so nothing
    actually fetched gets left out of the prompt by default just because
    it landed in a large priority group."""
    monkeypatch.delenv('TASK_OVERVIEW_MAX_PER_GROUP', raising=False)
    monkeypatch.delenv('MUSTERMEISTER_TASK_LIMIT', raising=False)
    config = Config()
    assert config.TASK_OVERVIEW_MAX_PER_GROUP == config.MUSTERMEISTER_TASK_LIMIT == 500


def test_task_overview_max_per_group_respects_env_override(monkeypatch):
    monkeypatch.setenv('TASK_OVERVIEW_MAX_PER_GROUP', '30')
    assert Config().TASK_OVERVIEW_MAX_PER_GROUP == 30


def test_ollama_num_ctx_defaults_to_8192(monkeypatch):
    monkeypatch.delenv('OLLAMA_NUM_CTX', raising=False)
    assert Config().OLLAMA_NUM_CTX == 8192


def test_ollama_num_ctx_respects_env_override(monkeypatch):
    monkeypatch.setenv('OLLAMA_NUM_CTX', '16384')
    assert Config().OLLAMA_NUM_CTX == 16384


def test_init_scheduler_registers_mustermeister_job_with_configured_interval(app, monkeypatch):
    monkeypatch.setattr(scheduler_module.config, 'is_main_process', True)
    monkeypatch.setattr(scheduler_module.config, 'MUSTERMEISTER_POLL_INTERVAL', 5)

    mock_scheduler = MagicMock()
    mock_scheduler.running = False

    scheduler_module.init_scheduler(app, mock_scheduler)

    call = next(
        call for call in mock_scheduler.add_job.call_args_list
        if call.args[0] is scheduler_module.refresh_mustermeister_tasks
    )
    assert call.kwargs['hours'] == 5
    # Must run immediately on startup -- this app isn't running 24/7, so
    # waiting out a possibly-missed interval boundary isn't good enough.
    assert 'next_run_time' in call.kwargs


def test_suggestion_queue_startup_run_is_delayed_behind_mustermeister_and_briefkorb(app, monkeypatch):
    """Regression test: at startup, refresh_mustermeister_tasks,
    refresh_briefkorb_messages, and refresh_suggestion_queue all used to
    get the same "now" next_run_time -- APScheduler's thread-pool executor
    can then run them concurrently in any order, so the queue refresh
    (which reads MustermeisterTaskCache/BriefKorbMessageCache) could read
    a still-stale cache from before the poll jobs finished, even though
    everything was technically "running" at startup. The queue refresh's
    startup run must be scheduled meaningfully later than the two poll
    jobs, not at the same instant."""
    monkeypatch.setattr(scheduler_module.config, 'is_main_process', True)

    mock_scheduler = MagicMock()
    mock_scheduler.running = False

    scheduler_module.init_scheduler(app, mock_scheduler)

    def next_run_time_for(job_func):
        call = next(c for c in mock_scheduler.add_job.call_args_list if c.args[0] is job_func)
        return call.kwargs['next_run_time']

    mustermeister_time = next_run_time_for(scheduler_module.refresh_mustermeister_tasks)
    briefkorb_time = next_run_time_for(scheduler_module.refresh_briefkorb_messages)
    suggestion_queue_time = next_run_time_for(scheduler_module.refresh_suggestion_queue)

    assert (suggestion_queue_time - mustermeister_time).total_seconds() >= \
        scheduler_module.SUGGESTION_QUEUE_STARTUP_DELAY_SECONDS
    assert (suggestion_queue_time - briefkorb_time).total_seconds() >= \
        scheduler_module.SUGGESTION_QUEUE_STARTUP_DELAY_SECONDS


def test_init_scheduler_registers_briefkorb_job_with_configured_interval(app, monkeypatch):
    monkeypatch.setattr(scheduler_module.config, 'is_main_process', True)
    monkeypatch.setattr(scheduler_module.config, 'BRIEFKORB_POLL_INTERVAL', 8)

    mock_scheduler = MagicMock()
    mock_scheduler.running = False

    scheduler_module.init_scheduler(app, mock_scheduler)

    call = next(
        call for call in mock_scheduler.add_job.call_args_list
        if call.args[0] is scheduler_module.refresh_briefkorb_messages
    )
    assert call.kwargs['hours'] == 8
    assert 'next_run_time' in call.kwargs


def test_run_immediately_kwargs_uses_a_near_now_datetime_not_a_stale_fixed_date():
    """Regression test for a real startup bug: a fixed past next_run_time
    (e.g. '2025-01-01 00:00:00') does NOT make a job run immediately --
    APScheduler's default misfire_grace_time is 1 second, so a next_run_time
    that far in the past is treated as *missed* and silently skipped
    (logged as a WARNING) rather than run, with the job's next fire time
    recomputed to the next regular interval boundary instead. next_run_time
    must be close to "now," and misfire_grace_time must be raised (None
    here) so ordinary startup latency between add_job() and the scheduler
    actually polling doesn't trip the same misfire path.
    """
    kwargs = scheduler_module._run_immediately_kwargs()

    assert kwargs['misfire_grace_time'] is None
    assert isinstance(kwargs['next_run_time'], datetime)
    assert (datetime.now() - kwargs['next_run_time']).total_seconds() < 5


def test_init_scheduler_registers_all_catch_up_jobs_with_unlimited_misfire_grace(app, monkeypatch):
    """Every job meant to catch up on startup must use the same
    misfire-proof kwargs, not just next_run_time on its own -- see
    _run_immediately_kwargs' docstring for why next_run_time alone isn't
    sufficient."""
    monkeypatch.setattr(scheduler_module.config, 'is_main_process', True)

    mock_scheduler = MagicMock()
    mock_scheduler.running = False

    scheduler_module.init_scheduler(app, mock_scheduler)

    catch_up_jobs = [
        scheduler_module.backfill_computed_calendar_events,
        scheduler_module.refresh_suggestion_queue,
        scheduler_module.refresh_mustermeister_tasks,
        scheduler_module.refresh_briefkorb_messages,
        scheduler_module.create_database_backup,
    ]
    for job_func in catch_up_jobs:
        call = next(c for c in mock_scheduler.add_job.call_args_list if c.args[0] is job_func)
        assert call.kwargs['misfire_grace_time'] is None, f'{job_func.__name__} missing misfire_grace_time=None'
        assert 'next_run_time' in call.kwargs, f'{job_func.__name__} missing next_run_time'


def test_init_scheduler_does_nothing_outside_the_main_werkzeug_process(app, monkeypatch):
    """The scheduler must not register jobs in a reloader watcher process --
    see the process-guard gotcha documented for create_app()/init_scheduler."""
    monkeypatch.setattr(scheduler_module.config, 'is_main_process', False)

    mock_scheduler = MagicMock()
    scheduler_module.init_scheduler(app, mock_scheduler)

    mock_scheduler.add_job.assert_not_called()
