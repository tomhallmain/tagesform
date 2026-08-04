import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services import planning_agent_service
from app.services.planning_agent_service import PLAN_SIGNAL_SOURCE_IDS, gather_plan_candidates
from extensions.llm import LLMResponseException

pytestmark = pytest.mark.unit


def _task_candidate(title, due_date, priority='medium', score=0.5):
    return {'item_type': 'task', 'source_id': 1, 'title': title, 'reason': '', 'score': score,
            'due_date': due_date, 'priority': priority}


def _email_candidate(title, sender_name, impact='high-impact', score=0.5):
    return {'item_type': 'email', 'source_id': 1, 'title': title, 'reason': '', 'score': score,
            'sender_name': sender_name, 'impact': impact, 'count': 1,
            'last_received_at': datetime(2026, 7, 30, 8, 0, 0)}


def _activity_candidate(title, scheduled_time, score=0.5):
    return {'item_type': 'activity', 'source_id': 1, 'title': title, 'reason': '', 'score': score,
            'scheduled_time': scheduled_time}


@pytest.fixture(autouse=True)
def enable_planning_agent(monkeypatch):
    monkeypatch.setattr(planning_agent_service.config, 'PLANNING_AGENT_ENABLED', True)


@pytest.fixture(autouse=True)
def no_weather_by_default():
    """Keep the today_overview signal from making a real network call in
    tests that don't care about weather -- get_current_weather() is called
    unconditionally whenever anything's on the calendar today."""
    with patch.object(planning_agent_service.integration_service, 'get_current_weather',
                       return_value={'error': 'not configured'}):
        yield


def test_gather_plan_candidates_returns_empty_when_disabled(monkeypatch, test_user):
    monkeypatch.setattr(planning_agent_service.config, 'PLANNING_AGENT_ENABLED', False)
    assert gather_plan_candidates(test_user, datetime(2026, 7, 30, 9, 0, 0), []) == []


def test_gather_plan_candidates_returns_empty_when_no_signals_qualify(test_user):
    assert gather_plan_candidates(test_user, datetime(2026, 7, 30, 9, 0, 0), []) == []


def test_task_overview_signal_falls_back_to_deterministic_text_when_llm_fails(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('Renew passport', now.date().replace(day=28))]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = [c for c in plan_candidates if c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['task_overview']]
    assert len(matching) == 1
    assert matching[0]['item_type'] == 'plan'


def test_task_overview_signal_uses_llm_phrasing_when_available(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('Renew passport', now.date().replace(day=28))]

    fake_result = MagicMock()
    fake_result.get_json_dict.return_value = {'title': 'One task on your plate', 'reason': 'Renew passport soon.'}
    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.return_value = fake_result
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = [c for c in plan_candidates if c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['task_overview']]
    assert matching[0]['title'] == 'One task on your plate'
    assert matching[0]['reason'] == 'Renew passport soon.'


def test_task_overview_signal_fires_regardless_of_due_date_or_priority(test_user):
    """Regression test: earlier versions of this signal filtered to
    overdue/due-today tasks, then to high-priority tasks -- both turned
    out to filter to nothing for a real account, since neither field is
    reliably populated there. Nothing should be excluded from this signal
    based on due_date or priority."""
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('No due date, no real priority', due_date=None, priority=None)]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    assert any(c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['task_overview'] for c in plan_candidates)


def test_task_overview_signal_absent_when_there_are_no_tasks(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    plan_candidates = gather_plan_candidates(test_user, now, [])

    assert not any(c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['task_overview'] for c in plan_candidates)


def test_task_overview_signal_states_priority_once_per_group_not_per_task(test_user):
    """The whole point of grouping by priority in the prompt: with N tasks
    sharing a priority, that priority is stated once (the group header),
    not N times -- this is what keeps a several-hundred-task backlog from
    blowing up the prompt."""
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [
        _task_candidate('High task A', due_date=None, priority='high'),
        _task_candidate('High task B', due_date=None, priority='high'),
        _task_candidate('High task C', due_date=None, priority='high'),
    ]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        gather_plan_candidates(test_user, now, candidates)

    prompt = mock_llm_cls.return_value.generate_response.call_args.args[0]
    assert prompt.count('Priority: high') == 1
    assert prompt.count('High task A') == 1


def test_task_overview_signal_groups_unset_priority_separately(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [
        _task_candidate('High task', due_date=None, priority='high'),
        _task_candidate('Unprioritized task', due_date=None, priority=None),
    ]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        gather_plan_candidates(test_user, now, candidates)

    prompt = mock_llm_cls.return_value.generate_response.call_args.args[0]
    assert 'Priority: high' in prompt
    assert 'Priority: unset' in prompt


def test_important_email_signal_produces_a_plan_item(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_email_candidate('Contract needs signature', 'Legal Team')]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = [c for c in plan_candidates if c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['important_unread_email']]
    assert len(matching) == 1


def test_today_overview_signal_absent_when_nothing_scheduled_today(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_activity_candidate('Next week thing', now.replace(day=6, month=8))]

    plan_candidates = gather_plan_candidates(test_user, now, candidates)

    assert not any(c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['today_overview'] for c in plan_candidates)


def test_today_overview_signal_present_when_something_scheduled_today(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_activity_candidate('Team standup', now.replace(hour=10))]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = [c for c in plan_candidates if c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['today_overview']]
    assert len(matching) == 1
    assert 'Team standup' in matching[0]['reason']


def test_one_failing_signal_does_not_prevent_others(test_user):
    """One signal builder raising must not take down the whole gather call --
    same per-source isolation convention as every other background job in
    this codebase."""
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [
        _task_candidate('Overdue task', now.date().replace(day=28)),
        _email_candidate('Important mail', 'Someone'),
    ]

    def broken_signal(*args, **kwargs):
        raise RuntimeError('boom')

    with patch.object(planning_agent_service, '_task_overview_signal', side_effect=broken_signal), \
         patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    assert any(c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['important_unread_email'] for c in plan_candidates)
    assert not any(c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['task_overview'] for c in plan_candidates)


def test_title_and_reason_are_truncated_to_column_limits(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('Overdue task', now.date().replace(day=28))]

    fake_result = MagicMock()
    fake_result.get_json_dict.return_value = {'title': 'x' * 500, 'reason': 'y' * 500}
    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.return_value = fake_result
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = next(c for c in plan_candidates if c['source_id'] == PLAN_SIGNAL_SOURCE_IDS['task_overview'])
    assert len(matching['title']) <= 200
    assert len(matching['reason']) <= 300
