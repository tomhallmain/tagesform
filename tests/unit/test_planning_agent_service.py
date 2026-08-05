import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.services import planning_agent_service
from app.services.planning_agent_service import (
    PLAN_SIGNAL_SOURCE_IDS, _stable_source_id, gather_plan_candidates,
)
from extensions.llm import LLMResponseException

pytestmark = pytest.mark.unit


def _source_id(signal_name, refs=None):
    """Computes the id a real candidate with these refs would get, via the
    actual implementation -- not a reimplementation of the hash, so this
    can't silently drift from what the code under test actually does."""
    return _stable_source_id(signal_name, refs or [])


def _fake_llm_result(*items):
    """items: (title, reason, refs) tuples. Mocks the shape
    LLMResult.get_json_dict() returns for the {"items": [...]} contract
    every signal's prompt asks for."""
    fake_result = MagicMock()
    fake_result.get_json_dict.return_value = {
        'items': [{'title': title, 'reason': reason, 'refs': refs} for title, reason, refs in items]
    }
    return fake_result


def _task_candidate(title, due_date, priority='medium', project=None, source_id=1, score=0.5):
    return {'item_type': 'task', 'source_id': source_id, 'title': title, 'reason': '', 'score': score,
            'due_date': due_date, 'priority': priority, 'project': project}


def _email_candidate(title, sender_name, impact='high-impact', source_id=1, score=0.5):
    return {'item_type': 'email', 'source_id': source_id, 'title': title, 'reason': '', 'score': score,
            'sender_name': sender_name, 'impact': impact, 'count': 1,
            'last_received_at': datetime(2026, 7, 30, 8, 0, 0)}


def _activity_candidate(title, scheduled_time, source_id=1, score=0.5):
    return {'item_type': 'activity', 'source_id': source_id, 'title': title, 'reason': '', 'score': score,
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

    matching = [c for c in plan_candidates if c['source_id'] == _source_id('task_overview')]
    assert len(matching) == 1
    assert matching[0]['item_type'] == 'plan'


def test_task_overview_signal_uses_llm_phrasing_when_available(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('Renew passport', now.date().replace(day=28))]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.return_value = _fake_llm_result(
            ('One task on your plate', 'Renew passport soon.', ['task:1'])
        )
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = [c for c in plan_candidates if c['source_id'] == _source_id('task_overview', ['task:1'])]
    assert matching[0]['title'] == 'One task on your plate'
    assert matching[0]['reason'] == 'Renew passport soon.'


def test_task_overview_signal_splits_multiple_llm_items_into_separate_candidates(test_user):
    """The LLM is allowed to return more than one title/reason pair (e.g.
    one standout task plus a summary of the rest) -- each must become its
    own 'plan' candidate with a distinct, deterministic source_id, not get
    collapsed into one or silently dropped."""
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [
        _task_candidate('Renew passport', now.date().replace(day=28), source_id=42),
        _task_candidate('Other task', due_date=None, source_id=99),
    ]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.return_value = _fake_llm_result(
            ('Passport renewal overdue', 'Renew passport was due 2026-07-28.', ['task:42']),
            ('12 other open tasks', 'Nothing else urgent.', ['task:99']),
        )
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = [c for c in plan_candidates if c['item_type'] == 'plan']
    assert len(matching) == 2
    by_title = {c['title']: c for c in matching}
    assert by_title['Passport renewal overdue']['source_id'] == _source_id('task_overview', ['task:42'])
    assert by_title['12 other open tasks']['source_id'] == _source_id('task_overview', ['task:99'])
    # distinct underlying tasks must never collide on the same id
    assert by_title['Passport renewal overdue']['source_id'] != by_title['12 other open tasks']['source_id']


def test_task_overview_signal_item_id_is_stable_regardless_of_order_or_wording(test_user):
    """The whole point of ref-based ids: the SAME underlying task keeps the
    SAME source_id even if the LLM phrases it differently, or returns it
    in a different position, on a later refresh."""
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('Renew passport', now.date().replace(day=28), source_id=42)]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.return_value = _fake_llm_result(
            ('Passport renewal overdue', 'Renew passport was due 2026-07-28.', ['task:42'])
        )
        first_pass = gather_plan_candidates(test_user, now, candidates)

        mock_llm_cls.return_value.generate_response.return_value = _fake_llm_result(
            ('Your passport needs renewing', 'It has been overdue since late July.', ['task:42'])
        )
        second_pass = gather_plan_candidates(test_user, now, candidates)

    first_id = next(c['source_id'] for c in first_pass if c['item_type'] == 'plan')
    second_id = next(c['source_id'] for c in second_pass if c['item_type'] == 'plan')
    assert first_id == second_id


def test_stable_source_id_is_independent_of_ref_order():
    a = _stable_source_id('task_overview', ['task:42', 'task:7'])
    b = _stable_source_id('task_overview', ['task:7', 'task:42'])
    assert a == b


def test_stable_source_id_does_not_collide_across_signals():
    a = _stable_source_id('task_overview', ['task:1'])
    b = _stable_source_id('important_unread_email', ['task:1'])
    assert a != b


def test_stable_source_id_general_item_is_stable_and_distinct_per_signal():
    a1 = _stable_source_id('task_overview', [])
    a2 = _stable_source_id('task_overview', [])
    b = _stable_source_id('important_unread_email', [])
    assert a1 == a2
    assert a1 != b


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

    assert any(c['source_id'] == _source_id('task_overview') for c in plan_candidates)


def test_task_overview_signal_absent_when_there_are_no_tasks(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    plan_candidates = gather_plan_candidates(test_user, now, [])

    assert not any(c['source_id'] == _source_id('task_overview') for c in plan_candidates)


def test_task_overview_signal_states_the_task_before_and_after_the_data(test_user):
    """The instructions must appear both before the task list (so the
    model knows what to look for while reading it) and after (restating
    the task plus the exact output format) -- not only at the very end of
    what can be a several-hundred-line prompt."""
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('Some task', due_date=None)]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        gather_plan_candidates(test_user, now, candidates)

    prompt = mock_llm_cls.return_value.generate_response.call_args.args[0]
    task_intro = "Look for what's actually worth their attention"
    assert prompt.count(task_intro) == 2
    task_before_idx = prompt.index(task_intro)
    data_idx = prompt.index('Some task')
    task_after_idx = prompt.rindex(task_intro)
    assert task_before_idx < data_idx < task_after_idx


def test_task_overview_signal_prompt_shows_output_format_with_an_example(test_user):
    """Naming the JSON keys alone leaves the model guessing what it's
    actually supposed to produce -- the prompt must show a concrete
    example of the exact shape, and state that returning one item or
    several is equally valid."""
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('Some task', due_date=None)]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        gather_plan_candidates(test_user, now, candidates)

    prompt = mock_llm_cls.return_value.generate_response.call_args.args[0]
    assert '"items"' in prompt
    assert 'Passport renewal is overdue' in prompt  # the concrete example
    assert 'or a mix of both' in prompt  # explicit permission for either shape


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


def test_task_overview_signal_subgroups_by_project_within_priority(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [
        _task_candidate('Fix bug', due_date=None, priority='high', project='Website'),
        _task_candidate('Add feature', due_date=None, priority='high', project='Website'),
        _task_candidate('Buy milk', due_date=None, priority='high', project='Home'),
    ]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        gather_plan_candidates(test_user, now, candidates)

    prompt = mock_llm_cls.return_value.generate_response.call_args.args[0]
    assert 'Priority: high' in prompt
    assert 'Project: Website (2 tasks)' in prompt
    assert 'Project: Home (1 task)' in prompt
    # project stated once for both tasks that share it, not repeated per task
    assert prompt.count('Project: Website') == 1


def test_task_overview_signal_groups_missing_project_separately(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('No project task', due_date=None, priority='high', project=None)]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        gather_plan_candidates(test_user, now, candidates)

    prompt = mock_llm_cls.return_value.generate_response.call_args.args[0]
    assert 'Project: no project' in prompt


def test_important_email_signal_produces_a_plan_item(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_email_candidate('Contract needs signature', 'Legal Team')]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = [c for c in plan_candidates if c['source_id'] == _source_id('important_unread_email')]
    assert len(matching) == 1


def test_today_overview_signal_absent_when_nothing_scheduled_today(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_activity_candidate('Next week thing', now.replace(day=6, month=8))]

    plan_candidates = gather_plan_candidates(test_user, now, candidates)

    assert not any(c['source_id'] == _source_id('today_overview') for c in plan_candidates)


def test_today_overview_signal_present_when_something_scheduled_today(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_activity_candidate('Team standup', now.replace(hour=10))]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.side_effect = LLMResponseException('down')
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = [c for c in plan_candidates if c['source_id'] == _source_id('today_overview')]
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

    assert any(c['source_id'] == _source_id('important_unread_email') for c in plan_candidates)
    assert not any(c['source_id'] == _source_id('task_overview') for c in plan_candidates)


def test_title_and_reason_are_truncated_to_column_limits(test_user):
    now = datetime(2026, 7, 30, 9, 0, 0)
    candidates = [_task_candidate('Overdue task', now.date().replace(day=28))]

    with patch.object(planning_agent_service, 'LLM') as mock_llm_cls:
        mock_llm_cls.return_value.generate_response.return_value = _fake_llm_result(
            ('x' * 500, 'y' * 500, ['task:1'])
        )
        plan_candidates = gather_plan_candidates(test_user, now, candidates)

    matching = next(c for c in plan_candidates if c['source_id'] == _source_id('task_overview', ['task:1']))
    assert len(matching['title']) <= 200
    assert len(matching['reason']) <= 300
