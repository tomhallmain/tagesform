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
-- the LLM is only ever asked to phrase human-readable title/reason pairs
for a bucket that's already known to be non-empty, never to invent bucket
membership from scratch. A signal may return more than one title/reason
pair (e.g. one specific standout item plus a summary of the rest) -- each
becomes its own SuggestionQueueItem, with source_id built from the
signal's base id and that item's position in the LLM's response (see
PLAN_ITEM_SOURCE_ID_STRIDE). That position is only as stable as the LLM's
own output: dismissing "item 2 of task_overview" reliably dismisses the
same underlying content next cycle only if the LLM keeps returning it in
that position, which isn't guaranteed -- a known, accepted trade-off of
letting the LLM decide how many things are worth surfacing, weaker than
the single-item stability every other candidate source in this app has.
"""

from datetime import date

from extensions.llm import LLM, LLMResponseException
from .integration_service import integration_service
from ..utils.config import config
from ..utils.logging_setup import get_logger
from ..utils.translations import _

logger = get_logger('planning_agent_service')

# Base id per signal. 'plan' items have no backing row (see
# SuggestionQueueItem's docstring) -- this constant, combined with an
# item's position within its signal's output (see
# PLAN_ITEM_SOURCE_ID_STRIDE), is this item_type's analogue of
# Activity.id/EventCache.id.
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

# Gives each signal's base id (PLAN_SIGNAL_SOURCE_IDS) room for up to this
# many items in one refresh before its source_id range would collide with
# the next signal's -- comfortably above anything these signals return.
PLAN_ITEM_SOURCE_ID_STRIDE = 1000

# Shared by every signal's prompt -- both what the output must look like
# (a real example, not just named keys) and that returning one item or
# several is equally valid, so the model isn't left guessing whether it's
# supposed to pick a single thing, compile everything into one summary, or
# both.
RESPONSE_FORMAT_INSTRUCTIONS = (
    'Respond with only a single JSON object with one key, "items": a list '
    'of one or more objects, each with a "title" and a "reason". Use one '
    'item to summarize everything at once, one item per specific thing '
    'worth calling out on its own (a task, a sender, a project, an event), '
    'or a mix of both -- whichever actually conveys what matters here. '
    'Each "title" is a short at-a-glance label (under 12 words); each '
    '"reason" is one or two sentences of concrete detail (under 40 words). '
    'Example of the exact shape (with placeholder content):\n'
    '{"items": [\n'
    '  {"title": "Passport renewal is overdue", "reason": "It was due '
    '2026-07-18, with nothing else competing for attention today."},\n'
    '  {"title": "31 low-priority tasks, mostly Website", "reason": '
    '"Nothing urgent, but this is the largest single group of open work."}\n'
    ']}\n'
    'No other text outside that JSON object.'
)


def gather_plan_candidates(user, now, candidates, active_schedule_category=None):
    """Returns a list of {item_type: 'plan', source_id, title, reason, score}
    dicts -- zero or more per signal, since a signal may return several
    title/reason pairs (see PLAN_ITEM_SOURCE_ID_STRIDE). `candidates` is
    the already-gathered activity/entity/event/task/email candidate list
    from this same refresh cycle (including their internal-only extra
    fields, e.g. due_date/scheduled_time) -- signals read from it rather
    than re-querying, so this never makes its own DB/API calls beyond the
    LLM itself.
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
            items = build_signal(now, candidates, active_schedule_category)
        except Exception as e:
            # One signal failing (LLM down, malformed data) must not cost
            # the other signals or the rest of the suggestion queue.
            logger.error(f"Error building plan signal '{signal_name}' for user {user.id}: {e}")
            continue
        if not items:
            continue
        for index, title_and_reason in enumerate(items):
            plan_candidates.append(_finalize_plan_candidate(signal_name, index, title_and_reason))
    return plan_candidates


def _finalize_plan_candidate(signal_name, index, title_and_reason):
    title, reason = title_and_reason
    return {
        'item_type': 'plan',
        'source_id': PLAN_SIGNAL_SOURCE_IDS[signal_name] * PLAN_ITEM_SOURCE_ID_STRIDE + index,
        'title': title[:TITLE_MAX_LENGTH],
        'reason': reason[:REASON_MAX_LENGTH],
        'score': PLAN_ITEM_SCORE,
    }


def _phrase_with_llm(prompt):
    """Ask the LLM to phrase one or more title/reason pairs for an
    already-decided, non-empty signal bucket. Returns a list of (title,
    reason) tuples, or None on any failure -- callers always have their
    own deterministic single-item fallback, so a down/slow/misbehaving LLM
    degrades the wording, not the presence, of a plan item that has real
    underlying data behind it."""
    try:
        llm = LLM(state_key='planning_agent')
        result = llm.generate_response(prompt)
        if result is None:
            return None
        parsed = result.get_json_dict()
        if not parsed:
            return None
        raw_items = parsed.get('items')
        if not isinstance(raw_items, list):
            return None
        items = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            title = str(raw_item.get('title', '')).strip()
            reason = str(raw_item.get('reason', '')).strip()
            if title and reason:
                items.append((title, reason))
        return items or None
    except LLMResponseException as e:
        logger.error(f"Planning agent LLM call failed: {e}")
        return None


TASK_OVERVIEW_PRIORITY_ORDER = ['high', 'medium', 'low', 'leisure']


def _task_overview_signal(now, candidates, active_schedule_category):
    """Every open task, grouped by Mustermeister's own `priority` field --
    no task is excluded based on due_date or priority. due_date in
    particular is often unset in practice, so filtering on it would make
    this signal fire rarely or never; the LLM sees the whole task list,
    organized for comparison, and decides what's actually worth
    surfacing, rather than code pre-deciding via a threshold on a field
    that may be sparse.

    Grouping by priority (and, within each priority, by project) also
    keeps token usage down for a large task list: each is stated once per
    group/subgroup header, not repeated on every task line.
    """
    tasks = [c for c in candidates if c['item_type'] == 'task']
    if not tasks:
        return None

    groups = _group_tasks_by_priority(tasks)

    # "at least" rather than an exact count -- MUSTERMEISTER_TASK_LIMIT can
    # truncate what actually got fetched (Mustermeister's own API reports
    # this via total_matching_count > limit, but that distinction isn't
    # threaded through the cache to here), so len(tasks) is a floor on the
    # real number of open tasks, not necessarily the real total.
    fallback_title = _('At least {0} open tasks').format(len(tasks))
    fallback_reason = ', '.join(f"{len(group_tasks)} {label}" for label, group_tasks in groups)

    section_blocks = []
    for label, group_tasks in groups:
        # Display cap, not a filter -- see config.TASK_OVERVIEW_MAX_PER_GROUP.
        # The header below always states the group's real count, even when
        # the listed tasks are capped below it. Applied once per priority
        # group (not per project) -- project is a presentation-level
        # subgrouping of whatever this cap already let through.
        shown = group_tasks[:config.TASK_OVERVIEW_MAX_PER_GROUP]

        project_blocks = []
        for project_label, project_tasks in _group_tasks_by_project(shown):
            lines = '\n'.join(
                f"  - {t['title']}" + (f" (due {t['due_date'].isoformat()})" if t.get('due_date') else '')
                for t in project_tasks
            )
            project_header = f"  Project: {project_label} ({len(project_tasks)} task{'s' if len(project_tasks) != 1 else ''})"
            project_blocks.append(f"{project_header}\n{lines}")

        header = f"Priority: {label} ({len(group_tasks)} task{'s' if len(group_tasks) != 1 else ''}"
        header += f", showing {len(shown)})" if len(shown) < len(group_tasks) else ")"
        section_blocks.append(header + '\n' + '\n'.join(project_blocks))
    tasks_block = '\n\n'.join(section_blocks)

    task = (
        "You are a planning assistant helping someone get a sense of their "
        "open tasks. Look for what's actually worth their attention -- "
        "specific tasks, specific projects, or the overall shape of the "
        "workload -- across everything below, grouped by priority and then "
        "by project."
    )
    prompt = (
        f"{task}\n\n"
        f"They have at least {len(tasks)} open tasks:\n\n"
        f"{tasks_block}\n\n"
        f"{task}\n\n"
        f"{RESPONSE_FORMAT_INSTRUCTIONS}"
    )
    return _phrase_with_llm(prompt) or [(fallback_title, fallback_reason)]


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


def _group_tasks_by_project(tasks):
    """Same shape as _group_tasks_by_priority, one level down: groups an
    already priority-grouped (and already capped) task list by the literal
    project string Mustermeister reports, falling back to a labeled "no
    project" bucket. No fixed ordering like TASK_OVERVIEW_PRIORITY_ORDER
    exists for project names, so groups are ordered by descending size,
    ties broken alphabetically for determinism."""
    groups = {}
    for task in tasks:
        label = task.get('project') or _('no project')
        groups.setdefault(label, []).append(task)

    ordered_labels = sorted(groups, key=lambda label: (-len(groups[label]), label))
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
    task = (
        "You are a planning assistant helping someone triage their inbox. "
        "Look for what's actually worth their attention -- specific "
        "senders or subjects, or the overall shape of what's waiting -- "
        "across the unread messages below."
    )
    prompt = (
        f"{task}\n\n"
        f"{email_lines}\n\n"
        f"{task}\n\n"
        f"{RESPONSE_FORMAT_INSTRUCTIONS}"
    )
    return _phrase_with_llm(prompt) or [(fallback_title, fallback_reason)]


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
    task = (
        "You are a planning assistant giving someone a quick orientation "
        "for their day. Look for what's actually worth mentioning -- "
        "specific events, the weather, or the overall shape of the day -- "
        "across what's below."
    )
    prompt = (
        f"{task}\n\n"
        f"{context_block}\n\n"
        f"{task}\n\n"
        f"{RESPONSE_FORMAT_INSTRUCTIONS}"
    )
    return _phrase_with_llm(prompt) or [(fallback_title, fallback_reason)]


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
