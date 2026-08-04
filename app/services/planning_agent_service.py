"""LLM-driven synthesis layer on top of the suggestion queue's raw
candidates -- joins calendar events, weather, and (when configured)
Mustermeister/BriefKorb candidates into a smaller number of higher-level
'plan' suggestions, rather than the queue only ever showing one row per raw
source item.

Gated on config.PLANNING_AGENT_ENABLED -- unlike the other candidate
sources, this makes a real LLM call (up to extensions.llm.LLM.DEFAULT_TIMEOUT
seconds) per non-empty signal per user on every suggestion queue refresh, so
it's opt-in rather than always-on.

Membership in each signal bucket below is decided deterministically in code
-- the LLM is only ever asked to phrase a human-readable title/reason for a
bucket that's already known to be non-empty, never to invent groupings on
its own. This keeps LLM output bounded to free text (robust: a bad response
just falls back to a plain deterministic phrasing) rather than needing the
LLM to reliably return well-formed groupings from scratch (fragile), and
keeps each signal's source_id stable across refreshes so dismissing a
'plan' item actually sticks -- the LLM's exact wording may vary run to run,
but which signal produced it doesn't.
"""

from datetime import date

from extensions.llm import LLM, LLMResponseException
from .integration_service import integration_service
from ..utils.config import config
from ..utils.logging_setup import get_logger
from ..utils.translations import _

logger = get_logger('planning_agent_service')

# Fixed, stable per-signal source_id. 'plan' items have no backing row (see
# SuggestionQueueItem's docstring) -- a small explicit constant per signal
# name is this item_type's analogue of Activity.id/EventCache.id, and is
# what makes refresh_queue_for_user's upsert-by-(item_type, source_id) find
# the same row again next cycle instead of creating a new one every time.
PLAN_SIGNAL_SOURCE_IDS = {
    'task_overview': 1,
    'important_unread_email': 2,
    'today_overview': 3,
}

# High enough to surface above most raw candidates (which top out well
# under 1.0 once boosts are applied) without unconditionally outranking
# every one of them regardless of the plan item's own content.
PLAN_ITEM_SCORE = 0.85

TITLE_MAX_LENGTH = 200   # matches SuggestionQueueItem.title's column length
REASON_MAX_LENGTH = 300  # matches SuggestionQueueItem.reason's column length


def gather_plan_candidates(user, now, candidates, active_schedule_category=None):
    """Returns a list of {item_type: 'plan', source_id, title, reason, score}
    dicts, one per non-empty signal bucket. `candidates` is the
    already-gathered activity/entity/event/task/email candidate list from
    this same refresh cycle (including their internal-only extra fields,
    e.g. due_date/scheduled_time) -- signals read from it rather than
    re-querying, so this never makes its own DB/API calls beyond the LLM
    itself.
    """
    if not config.PLANNING_AGENT_ENABLED:
        return []

    signal_builders = (
        ('task_overview', _task_overview_signal),
        ('important_unread_email', _important_unread_email_signal),
        ('today_overview', _today_overview_signal),
    )

    plan_candidates = []
    for signal_name, build_signal in signal_builders:
        try:
            candidate = build_signal(now, candidates, active_schedule_category)
        except Exception as e:
            # One signal failing (LLM down, malformed data) must not cost
            # the other signals or the rest of the suggestion queue.
            logger.error(f"Error building plan signal '{signal_name}' for user {user.id}: {e}")
            continue
        if candidate is not None:
            plan_candidates.append(_finalize_plan_candidate(signal_name, candidate))
    return plan_candidates


def _finalize_plan_candidate(signal_name, title_and_reason):
    title, reason = title_and_reason
    return {
        'item_type': 'plan',
        'source_id': PLAN_SIGNAL_SOURCE_IDS[signal_name],
        'title': title[:TITLE_MAX_LENGTH],
        'reason': reason[:REASON_MAX_LENGTH],
        'score': PLAN_ITEM_SCORE,
    }


def _phrase_with_llm(prompt):
    """Ask the LLM to phrase a title/reason pair for an already-decided,
    non-empty signal bucket. Returns a (title, reason) tuple, or None on any
    failure -- callers always have their own deterministic fallback text,
    so a down/slow/misbehaving LLM degrades the wording, not the presence,
    of a plan item that has real underlying data behind it."""
    try:
        llm = LLM(state_key='planning_agent')
        result = llm.generate_response(prompt)
        if result is None:
            return None
        parsed = result.get_json_dict()
        if not parsed:
            return None
        title = str(parsed.get('title', '')).strip()
        reason = str(parsed.get('reason', '')).strip()
        if not title or not reason:
            return None
        return title, reason
    except LLMResponseException as e:
        logger.error(f"Planning agent LLM call failed: {e}")
        return None


TASK_OVERVIEW_PRIORITY_ORDER = ['high', 'medium', 'low', 'leisure']
# Per-group cap so a several-hundred-task backlog doesn't get dumped
# verbatim into the prompt -- this only limits how many *lines* are shown
# within a group, not which tasks/groups qualify to be shown at all. Group
# headers always state the group's real total, even when truncated below it.
TASK_OVERVIEW_MAX_PER_GROUP = 15


def _task_overview_signal(now, candidates, active_schedule_category):
    """Every open task, grouped by Mustermeister's own `priority` field --
    no task is excluded based on due_date or priority. due_date in
    particular is often unset in practice, so filtering on it would make
    this signal fire rarely or never; the LLM sees the whole task list,
    organized for comparison, and decides what's actually worth
    surfacing, rather than code pre-deciding via a threshold on a field
    that may be sparse.

    Grouping by priority also keeps token usage down for a large task
    list: the priority is stated once per group header, not repeated on
    every task line.
    """
    tasks = [c for c in candidates if c['item_type'] == 'task']
    if not tasks:
        return None

    groups = _group_tasks_by_priority(tasks)

    fallback_title = _('{0} open tasks').format(len(tasks))
    fallback_reason = ', '.join(f"{len(group_tasks)} {label}" for label, group_tasks in groups)

    section_blocks = []
    for label, group_tasks in groups:
        shown = group_tasks[:TASK_OVERVIEW_MAX_PER_GROUP]
        lines = '\n'.join(
            f"- {t['title']}" + (f" (due {t['due_date'].isoformat()})" if t.get('due_date') else '')
            for t in shown
        )
        header = f"Priority: {label} ({len(group_tasks)} task{'s' if len(group_tasks) != 1 else ''}"
        header += f", showing {len(shown)})" if len(shown) < len(group_tasks) else ")"
        section_blocks.append(f"{header}\n{lines}")
    tasks_block = '\n\n'.join(section_blocks)

    prompt = (
        "You are a planning assistant helping someone get a sense of their "
        f"open tasks. They have {len(tasks)} open tasks in total, grouped "
        "by priority below:\n\n"
        f"{tasks_block}\n\n"
        'Respond with only a single JSON object with exactly two keys: '
        '"title" (a short at-a-glance label, under 12 words) and "reason" '
        '(one or two sentences giving a genuinely useful sense of the '
        'workload -- call out specific items with due dates if any stand '
        'out, otherwise characterize the overall picture, under 40 words). '
        'No other text.'
    )
    return _phrase_with_llm(prompt) or (fallback_title, fallback_reason)


def _group_tasks_by_priority(tasks):
    """Groups by the literal priority string Mustermeister reports
    (falling back to a labeled "unset" bucket for None/empty), sorted
    within each group by due_date (soonest first, undated tasks last) then
    title. Groups are ordered by TASK_OVERVIEW_PRIORITY_ORDER first, then
    any other value seen (including "unset") by descending group size."""
    groups = {}
    for task in tasks:
        label = task.get('priority') or _('unset')
        groups.setdefault(label, []).append(task)

    for group_tasks in groups.values():
        group_tasks.sort(key=lambda t: (t.get('due_date') or date.max, t['title']))

    ordered_labels = [p for p in TASK_OVERVIEW_PRIORITY_ORDER if p in groups]
    ordered_labels += sorted(
        (label for label in groups if label not in TASK_OVERVIEW_PRIORITY_ORDER),
        key=lambda label: -len(groups[label]),
    )
    return [(label, groups[label]) for label in ordered_labels]


def _important_unread_email_signal(now, candidates, active_schedule_category):
    important = sorted(
        (c for c in candidates if c['item_type'] == 'email'),
        key=lambda c: c['score'], reverse=True,
    )
    if not important:
        return None

    fallback_title = (
        important[0]['title'] if len(important) == 1
        else _('{0} important unread emails').format(len(important))
    )
    fallback_reason = ', '.join(c.get('sender_name') or c['title'] for c in important[:5])

    email_lines = '\n'.join(
        f"- From {c.get('sender_name') or 'an unknown sender'}: \"{c['title']}\" "
        f"(impact: {c.get('impact') or 'unclassified'})"
        for c in important
    )
    prompt = (
        "You are a planning assistant helping someone triage their inbox. "
        "Here are unread emails worth their attention today:\n\n"
        f"{email_lines}\n\n"
        'Respond with only a single JSON object with exactly two keys: '
        '"title" (a short at-a-glance label, under 12 words) and "reason" '
        '(one sentence naming the most important sender(s)/subject(s), '
        'under 30 words). No other text.'
    )
    return _phrase_with_llm(prompt) or (fallback_title, fallback_reason)


def _today_overview_signal(now, candidates, active_schedule_category):
    today = now.date()
    todays_activities = [
        c for c in candidates if c['item_type'] == 'activity' and c['scheduled_time'].date() == today
    ]
    todays_events = [
        c for c in candidates if c['item_type'] == 'event' and c['event_date'].date() == today
    ]
    items_today = todays_activities + todays_events
    if not items_today:
        # Nothing on the calendar today -- no overview worth generating.
        # (Deliberately not folding in weather/schedule-category alone;
        # those without anything scheduled aren't a "plan" so much as
        # ambient dashboard context the weather widget already shows.)
        return None

    weather_line = _weather_summary_line()
    items_today.sort(key=lambda c: c['scheduled_time'] if c['item_type'] == 'activity' else c['event_date'])

    fallback_title = _("Today's plan ({0} items)").format(len(items_today))
    fallback_reason_bits = [c['title'] for c in items_today[:4]]
    if weather_line:
        fallback_reason_bits.append(weather_line)
    fallback_reason = ', '.join(fallback_reason_bits)

    item_lines = '\n'.join(
        f"- {c['title']} at "
        f"{(c['scheduled_time'] if c['item_type'] == 'activity' else c['event_date']).strftime('%H:%M')}"
        for c in items_today
    )
    context_lines = [f"Today's schedule:\n{item_lines}"]
    if weather_line:
        context_lines.append(f"Weather: {weather_line}")
    if active_schedule_category:
        context_lines.append(f"Currently in a '{active_schedule_category}' schedule block.")

    context_block = '\n'.join(context_lines)
    prompt = (
        "You are a planning assistant giving someone a quick orientation for "
        "their day. Here's what's relevant:\n\n"
        f"{context_block}\n\n"
        'Respond with only a single JSON object with exactly two keys: '
        '"title" (a short at-a-glance label for today, under 12 words) and '
        '"reason" (one or two sentences orienting them to today\'s day, '
        'weaving in the weather if it is notable, under 40 words). No other text.'
    )
    return _phrase_with_llm(prompt) or (fallback_title, fallback_reason)


def _weather_summary_line():
    try:
        weather = integration_service.get_current_weather()
    except Exception as e:
        logger.error(f"Error fetching weather for planning agent: {e}")
        return None
    if not weather or weather.get('error'):
        return None

    parts = []
    if weather.get('description'):
        parts.append(weather['description'])
    if weather.get('temperature') is not None:
        parts.append(f"{weather['temperature']}°F")
    if weather.get('rain'):
        parts.append(f"rain: {weather['rain']}")
    return ', '.join(parts) if parts else None
