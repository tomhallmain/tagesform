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
pair (e.g. one specific standout item plus a summary of the rest); each
becomes its own SuggestionQueueItem. Its source_id is derived from what
the item is actually about -- the specific tasks/emails/events (or, for a
compiled item, a whole priority group) the LLM tags it with via "refs" --
not from its position in the LLM's response or its exact wording (see
_stable_source_id). Dismissing "the passport task" stays dismissed as
long as it's still the same underlying task, regardless of how the LLM's
summary reshuffles or rephrases around it from one refresh to the next.
"""

import zlib
from datetime import date

from extensions.llm import LLM, LLMResponseException
from .integration_service import integration_service
from ..utils.config import config
from ..utils.logging_setup import get_logger
from ..utils.translations import _

logger = get_logger('planning_agent_service')

# Base id per signal. 'plan' items have no backing row (see
# SuggestionQueueItem's docstring) -- combined with a content-derived hash
# of what a given item is about (see _stable_source_id), this is that
# item_type's analogue of Activity.id/EventCache.id.
PLAN_SIGNAL_SOURCE_IDS = {
    'task_overview': 1,
    'important_unread_email': 2,
    'today_overview': 3,
}

# zlib.crc32 (used by _stable_source_id) always fits in 32 bits -- this
# gives each signal's base id its own non-overlapping block of the id
# space to add that hash into.
PLAN_SIGNAL_ID_SPACE = 2 ** 32

# High enough to surface above most raw candidates (which top out well
# under 1.0 once boosts are applied) without unconditionally outranking
# every one of them regardless of the plan item's own content.
PLAN_ITEM_SCORE = 0.85

TITLE_MAX_LENGTH = 200   # matches SuggestionQueueItem.title's column length
REASON_MAX_LENGTH = 300  # matches SuggestionQueueItem.reason's column length

# Shared by every signal's prompt -- both what the output must look like
# (a real example, not just named keys) and that returning one item or
# several is equally valid, so the model isn't left guessing whether it's
# supposed to pick a single thing, compile everything into one summary, or
# both. "refs" is what makes a returned item's identity stable across
# refreshes -- see _stable_source_id -- so every signal's data is tagged
# with the exact strings an item's "refs" should echo back.
RESPONSE_FORMAT_INSTRUCTIONS = (
    'Respond with only a single JSON object with one key, "items": a list '
    'of one or more objects, each with "title", "reason", and "refs". Use '
    'one item to summarize everything at once, one item per specific thing '
    'worth calling out on its own, or a mix of both -- whichever actually '
    'conveys what matters here. "refs" is a list of the exact bracketed '
    'tags (e.g. "task:42") shown next to whatever this item is about -- '
    'include every tag that applies for a compiled/summary item, or an '
    'empty list [] only if the item is genuinely general and not about '
    'anything specific shown. Each "title" is a short at-a-glance label '
    '(under 12 words); each "reason" is one or two sentences of concrete '
    'detail (under 40 words). Example of the exact shape (with placeholder '
    'content):\n'
    '{"items": [\n'
    '  {"title": "Passport renewal is overdue", "reason": "It was due '
    '2026-07-18, with nothing else competing for attention today.", '
    '"refs": ["task:42"]},\n'
    '  {"title": "31 low-priority tasks, mostly Website", "reason": '
    '"Nothing urgent, but this is the largest single group of open work.", '
    '"refs": ["priority:low"]}\n'
    ']}\n'
    'No other text outside that JSON object.'
)


def gather_plan_candidates(user, now, candidates, active_schedule_category=None):
    """Returns a list of {item_type: 'plan', source_id, title, reason, score}
    dicts -- zero or more per signal, since a signal may return several
    title/reason pairs. `candidates` is the already-gathered activity/
    entity/event/task/email candidate list from this same refresh cycle
    (including their internal-only extra fields, e.g. due_date/
    scheduled_time) -- signals read from it rather than re-querying, so
    this never makes its own DB/API calls beyond the LLM itself.
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
        for title, reason, refs in items:
            plan_candidates.append(_finalize_plan_candidate(signal_name, title, reason, refs))
    return plan_candidates


def _stable_source_id(signal_name, refs):
    """Deterministic source_id for a 'plan' item, derived from what it's
    about (refs) rather than its position in the LLM's response or its
    exact wording, either of which can change between calls even when the
    underlying content hasn't. refs=[] (a genuinely general item, not tied
    to anything specific) maps every such item from the same signal to the
    same id -- there's no finer-grained identity available for "general
    commentary." Stability still ultimately depends on the LLM tagging the
    same content the same way call to call, same as everything else about
    what it chooses to say -- this removes the *position/wording*
    instability on top of that, it doesn't make LLM output perfectly
    deterministic.
    """
    canonical = ','.join(sorted(str(ref) for ref in refs)) or '__general__'
    content_hash = zlib.crc32(canonical.encode('utf-8'))
    return PLAN_SIGNAL_SOURCE_IDS[signal_name] * PLAN_SIGNAL_ID_SPACE + content_hash


def _finalize_plan_candidate(signal_name, title, reason, refs):
    return {
        'item_type': 'plan',
        'source_id': _stable_source_id(signal_name, refs),
        'title': title[:TITLE_MAX_LENGTH],
        'reason': reason[:REASON_MAX_LENGTH],
        'score': PLAN_ITEM_SCORE,
    }


def _phrase_with_llm(prompt):
    """Ask the LLM to phrase one or more title/reason/refs triples for an
    already-decided, non-empty signal bucket. Returns a list of (title,
    reason, refs) tuples, or None on any failure -- callers always have
    their own deterministic single-item fallback, so a down/slow/
    misbehaving LLM degrades the wording, not the presence, of a plan item
    that has real underlying data behind it."""
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
            if not title or not reason:
                continue
            raw_refs = raw_item.get('refs')
            refs = [str(ref) for ref in raw_refs] if isinstance(raw_refs, list) else []
            items.append((title, reason, refs))
        return items or None
    except LLMResponseException as e:
        logger.error(f"Planning agent LLM call failed: {e}")
        return None


TASK_OVERVIEW_PRIORITY_ORDER = ['high', 'medium', 'low', 'leisure']
# Workflow order for the handful of status names common enough to be worth
# a fixed position; anything else (a project-specific status) falls back
# to descending-size ordering, appended after all of these -- see
# _group_tasks_by_label/_group_tasks_by_status.
TASK_OVERVIEW_STATUS_ORDER = ['Not Started', 'To Investigate', 'In Progress', 'Ready to Test']
# Statuses whose tasks are mostly already done -- these still appear (never
# excluded, same as everything else in this signal), but the prompt asks
# the model to weight them lower, since a big bucket of them isn't as
# noteworthy as the same-size bucket in an earlier-stage status.
TASK_OVERVIEW_DEPRIORITIZED_STATUSES = ['Ready to Test']


def _task_overview_signal(now, candidates, active_schedule_category):
    """Every open task, grouped by Mustermeister's own `priority` field,
    then `status`, then `project` -- no task is excluded based on any of
    these or on due_date. due_date and priority are both often unset in
    practice, so filtering on either would make this signal fire rarely or
    never; the LLM sees the whole task list, organized for comparison, and
    decides what's actually worth surfacing, rather than code
    pre-deciding via a threshold on a field that may be sparse.

    Status comes before project in the nesting (not the other way around,
    and not flattened into a per-task detail) because tasks are expected
    to clump by status more than by project -- and status was previously
    dropped from this signal entirely, losing real information. Only
    priority is independently referenceable in "refs" (as
    [priority:LABEL]) -- status and project values repeat across
    priority groups, so a bare "status:X" or "project:X" tag would be
    ambiguous about which priority group it means; task-level refs
    ([task:ID]) are always available for anything more specific than a
    whole priority group.

    Grouping this way also keeps token usage down for a large task list:
    each priority/status/project is stated once per group header, not
    repeated on every task line.

    The prompt also asks the LLM to weight TASK_OVERVIEW_DEPRIORITIZED_STATUSES
    (e.g. 'Ready to Test') lower than earlier-stage work -- a bias in the
    LLM's judgment, not a membership exclusion; those tasks are still shown
    and can still be mentioned.
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
    for priority_label, group_tasks in groups:
        # Display cap, not a filter -- see config.TASK_OVERVIEW_MAX_PER_GROUP.
        # The header below always states the group's real count, even when
        # the listed tasks are capped below it. Applied once per priority
        # group -- status/project are presentation-level subgroupings of
        # whatever this cap already let through.
        shown = group_tasks[:config.TASK_OVERVIEW_MAX_PER_GROUP]

        status_blocks = []
        for status_label, status_tasks in _group_tasks_by_status(shown):
            project_blocks = []
            for project_label, project_tasks in _group_tasks_by_project(status_tasks):
                lines = '\n'.join(
                    f"      - [task:{t['source_id']}] {t['title']}"
                    + (f" (due {t['due_date'].isoformat()})" if t.get('due_date') else '')
                    for t in project_tasks
                )
                project_header = (
                    f"    Project: {project_label} "
                    f"({len(project_tasks)} task{'s' if len(project_tasks) != 1 else ''})"
                )
                project_blocks.append(f"{project_header}\n{lines}")
            status_header = f"  Status: {status_label} ({len(status_tasks)} task{'s' if len(status_tasks) != 1 else ''})"
            status_blocks.append(status_header + '\n' + '\n'.join(project_blocks))

        header = f"Priority: {priority_label} [priority:{priority_label}] ({len(group_tasks)} task{'s' if len(group_tasks) != 1 else ''}"
        header += f", showing {len(shown)})" if len(shown) < len(group_tasks) else ")"
        section_blocks.append(header + '\n' + '\n'.join(status_blocks))
    tasks_block = '\n\n'.join(section_blocks)

    deprioritized_statuses = ', '.join(f"'{s}'" for s in TASK_OVERVIEW_DEPRIORITIZED_STATUSES)
    task = (
        "You are a planning assistant helping someone get a sense of their "
        "open tasks. Look for what's actually worth their attention -- "
        "specific tasks, specific statuses, specific projects, or the "
        "overall shape of the workload -- across everything below, "
        "grouped by priority, then status, then project. Focus mainly on "
        "earlier-stage statuses (e.g. 'Not Started', 'To Investigate', "
        f"'In Progress'); a task in {deprioritized_statuses} means the "
        "work itself is largely already done, so a large group there is "
        "rarely as noteworthy as the same size group in an earlier "
        "status -- still fine to mention if genuinely nothing else "
        "stands out, just don't lead with it purely because of size. "
        "Each task is tagged [task:ID]; each priority group is tagged "
        "[priority:LABEL]."
    )
    prompt = (
        f"{task}\n\n"
        f"They have at least {len(tasks)} open tasks:\n\n"
        f"{tasks_block}\n\n"
        f"{task}\n\n"
        f"{RESPONSE_FORMAT_INSTRUCTIONS}"
    )
    return _phrase_with_llm(prompt) or [(fallback_title, fallback_reason, [])]


def _group_tasks_by_label(tasks, field_name, fallback_label, fixed_order=None):
    """Groups tasks by the literal string Mustermeister reports for
    `field_name`, falling back to `fallback_label` when unset. If
    `fixed_order` is given, groups matching one of its values come first,
    in that order; any other value seen (including the fallback, and any
    project-/account-specific value that doesn't match a known one) is
    appended after, ordered by descending group size, ties broken
    alphabetically for determinism. Without `fixed_order` (project has no
    real-world ordering the way priority/status do), every group is
    ordered that same descending-size-then-alphabetical way."""
    groups = {}
    for task in tasks:
        label = task.get(field_name) or fallback_label
        groups.setdefault(label, []).append(task)

    fixed_order = fixed_order or []
    ordered_labels = [label for label in fixed_order if label in groups]
    ordered_labels += sorted(
        (label for label in groups if label not in fixed_order),
        key=lambda label: (-len(groups[label]), label),
    )
    return [(label, groups[label]) for label in ordered_labels]


def _group_tasks_by_priority(tasks):
    """Ordered by TASK_OVERVIEW_PRIORITY_ORDER (see _group_tasks_by_label),
    with each group additionally sorted by due_date (soonest first,
    undated tasks last) then title -- priority is the only level with a
    meaningful per-task ordering within its groups; status/project are
    just membership splits."""
    groups = _group_tasks_by_label(tasks, 'priority', _('unset'), fixed_order=TASK_OVERVIEW_PRIORITY_ORDER)
    for _label, group_tasks in groups:
        group_tasks.sort(key=lambda t: (t.get('due_date') or date.max, t['title']))
    return groups


def _group_tasks_by_status(tasks):
    """Ordered by TASK_OVERVIEW_STATUS_ORDER -- Mustermeister's own status
    names are per-project/per-account custom values, not a fixed set the
    way priority is, but a handful of common ones have a natural workflow
    order worth respecting when present; anything else falls back to
    descending-size ordering (see _group_tasks_by_label)."""
    return _group_tasks_by_label(tasks, 'status', _('no status'), fixed_order=TASK_OVERVIEW_STATUS_ORDER)


def _group_tasks_by_project(tasks):
    return _group_tasks_by_label(tasks, 'project', _('no project'))


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
        f"- [email:{c['source_id']}] From {c.get('sender_name') or 'an unknown sender'}: "
        f"\"{c['title']}\" (impact: {c.get('impact') or 'unclassified'})"
        for c in important
    )
    task = (
        "You are a planning assistant helping someone triage their inbox. "
        "Look for what's actually worth their attention -- specific "
        "senders or subjects, or the overall shape of what's waiting -- "
        "across the unread messages below. Each message is tagged "
        "[email:ID]."
    )
    prompt = (
        f"{task}\n\n"
        f"{email_lines}\n\n"
        f"{task}\n\n"
        f"{RESPONSE_FORMAT_INSTRUCTIONS}"
    )
    return _phrase_with_llm(prompt) or [(fallback_title, fallback_reason, [])]


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
        f"- [{c['item_type']}:{c['source_id']}] {c['title']} at "
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
        "across what's below. Each calendar item is tagged [activity:ID] "
        "or [event:ID]."
    )
    prompt = (
        f"{task}\n\n"
        f"{context_block}\n\n"
        f"{task}\n\n"
        f"{RESPONSE_FORMAT_INSTRUCTIONS}"
    )
    return _phrase_with_llm(prompt) or [(fallback_title, fallback_reason, [])]


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
