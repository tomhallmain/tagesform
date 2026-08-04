import pytest
from datetime import timedelta
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


def test_init_scheduler_does_nothing_outside_the_main_werkzeug_process(app, monkeypatch):
    """The scheduler must not register jobs in a reloader watcher process --
    see the process-guard gotcha documented for create_app()/init_scheduler."""
    monkeypatch.setattr(scheduler_module.config, 'is_main_process', False)

    mock_scheduler = MagicMock()
    scheduler_module.init_scheduler(app, mock_scheduler)

    mock_scheduler.add_job.assert_not_called()
