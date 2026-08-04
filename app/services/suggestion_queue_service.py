"""Candidate-gathering and scoring for the suggestion queue.

Draws on the calendar/entity work built up over this project: activities,
entities (rating/open-now, independently recomputed here rather than via
entities.py's request-scoped lru_cache helpers), and IntegrationService.
get_calendar_events -- which by now already merges public holidays, Hebrew/
USNO/Nobel Prize/rocket-launch events, a user's own custom calendar, and any
entity's calendar entries the user can see, so reusing it here means the
suggestion queue automatically benefits from all of that instead of
re-deriving its own narrower view of "what events exist."

item_type is intentionally open-ended (see SuggestionQueueItem's docstring).
'task'/'email' candidates (_task_candidates/_email_candidates) come from
local caches of two external, same-owner projects -- Mustermeister (task
manager) and BriefKorb (email) -- populated by their own background jobs;
see docs/task-email-integration.md. Both are gated on
config.TASK_EMAIL_INTEGRATION_USER_ID (a single integration owner, not
per-user account linking), so they return [] for every other user.

'plan' candidates (_plan_candidates) are a further synthesis step on top of
all of the above -- see planning_agent_service.py -- joining calendar
events, weather, and task/email candidates via an LLM into a smaller number
of higher-level suggestions, rather than one row per raw source item.
"""

from datetime import datetime, timedelta

from ..models import Activity, BriefKorbMessageCache, Entity, MustermeisterTaskCache, SuggestionQueueItem, db
from .integration_service import integration_service
from .schedules_manager import SchedulesManager
from ..utils.config import config
from ..utils.geo import haversine_miles
from ..utils.translations import _

ACTIVITY_LOOKAHEAD_DAYS = 14
EVENT_LOOKAHEAD_DAYS = 14
TASK_DUE_LOOKAHEAD_DAYS = 14
# Matches BriefKorb's own /api/messages staleAfterDays default (3.0) -- the
# same window BriefKorb itself uses to judge a message "stale" is a
# reasonable window for our own recency decay.
EMAIL_RECENCY_WINDOW_DAYS = 3

TASK_PRIORITY_WEIGHTS = {'leisure': 1, 'low': 2, 'medium': 3, 'high': 4}
EMAIL_IMPACT_TIER_WEIGHTS = {'high-impact': 1.0, 'unclassified': 0.5, 'low-impact': 0.0}

# Default radius (miles) for _entity_candidates' hard proximity filter, for
# any user who hasn't set their own 'nearby_distance_miles' preference --
# see docs/entity-geolocation.md. settings.py imports this rather than
# defining its own copy, so the form's displayed default and the value
# actually applied here can't drift apart.
DEFAULT_NEARBY_DISTANCE_MILES = 25


def gather_candidates_for_user(user, now=None):
    """Returns a list of dicts: {item_type, source_id, title, reason, score}."""
    now = now or datetime.utcnow()
    candidates = []
    candidates.extend(_activity_candidates(user, now))
    candidates.extend(_entity_candidates(user, now))
    candidates.extend(_event_candidates(user, now))
    candidates.extend(_task_candidates(user, now))
    candidates.extend(_email_candidates(user, now))
    candidates.extend(_plan_candidates(user, now, candidates))
    return candidates


def _task_email_integration_enabled_for(user):
    """Mustermeister/BriefKorb are configured for a single integration
    owner, not per-user account linking -- see
    docs/task-email-integration.md. Returns [] from every candidate
    gated on this for every other user of a multi-user install."""
    return (
        config.TASK_EMAIL_INTEGRATION_USER_ID is not None
        and user.id == config.TASK_EMAIL_INTEGRATION_USER_ID
    )


def _favorite_categories(user):
    """User.preferences doesn't currently have a 'favorite categories' field
    -- nothing in settings.py writes one. Checking for it anyway costs
    nothing (a plain dict .get on JSON that may not have the key) and means
    this signal activates automatically if such a preference is ever added,
    rather than needing this scoring code to change too."""
    preferences = user.preferences or {}
    favorites = preferences.get('favorite_categories')
    return set(favorites) if favorites else set()


def _nearby_distance_miles(user):
    """Per-user preference (User.preferences JSON, same mechanism as
    favorite_categories) for _entity_candidates' hard proximity cutoff --
    falls back to DEFAULT_NEARBY_DISTANCE_MILES when unset or invalid."""
    preferences = user.preferences or {}
    value = preferences.get('nearby_distance_miles')
    if value is None:
        return DEFAULT_NEARBY_DISTANCE_MILES
    try:
        return float(value)
    except (TypeError, ValueError):
        return DEFAULT_NEARBY_DISTANCE_MILES


def _active_schedule_category(user, now):
    try:
        schedule = SchedulesManager.get_active_schedule(now, user.id)
    except Exception:
        return None
    return getattr(schedule, 'category', None)


def _activity_candidates(user, now):
    favorites = _favorite_categories(user)
    active_category = _active_schedule_category(user, now)

    activities = Activity.query.filter(
        Activity.user_id == user.id,
        Activity.status == 'upcoming',
        Activity.scheduled_time >= now,
        Activity.scheduled_time <= now + timedelta(days=ACTIVITY_LOOKAHEAD_DAYS),
    ).all()

    candidates = []
    for activity in activities:
        importance = activity.importance if activity.importance is not None else 0.5
        days_until = max((activity.scheduled_time - now).total_seconds() / 86400.0, 0.0)
        proximity_score = max(0.0, 1.0 - (days_until / ACTIVITY_LOOKAHEAD_DAYS))
        score = 0.6 * importance + 0.4 * proximity_score

        reason_bits = []
        if days_until < 1:
            reason_bits.append(_('Due today'))
        else:
            reason_bits.append(_('In {0} days').format(int(days_until) + 1))
        if importance >= 0.7:
            reason_bits.append(_('high importance'))
            score += 0.1
        if activity.category and activity.category == active_category:
            reason_bits.append(_('matches your current schedule'))
            score += 0.15
        if activity.category and activity.category in favorites:
            reason_bits.append(_('a favorite category'))
            score += 0.15

        candidates.append({
            'item_type': 'activity',
            'source_id': activity.id,
            'title': activity.title,
            'reason': ', '.join(reason_bits),
            'score': score,
            'scheduled_time': activity.scheduled_time,  # internal-only, read by planning_agent_service
        })
    return candidates


def _is_entity_open(entity, current_day, current_hour):
    """Independent of entities.py's get_open_entities -- that helper (and
    its lru_cache wrapper) is request-scoped and keyed off current_user,
    neither of which exists in this background-job context. Mirrors the
    same "missing/invalid hours means assume open" convention for
    consistency with what the dashboard already shows."""
    if not entity.operating_hours or current_day not in entity.operating_hours:
        return True
    hours = entity.operating_hours[current_day]
    if not hours or not hours.get('open') or not hours.get('close'):
        return True
    try:
        open_hour = int(hours['open'].split(':')[0])
        close_hour = int(hours['close'].split(':')[0])
        if close_hour < open_hour:
            close_hour += 24
        return open_hour <= current_hour < close_hour
    except (ValueError, IndexError, AttributeError):
        return True


def _entity_candidates(user, now):
    favorites = _favorite_categories(user)
    nearby_distance_miles = _nearby_distance_miles(user)
    entities = Entity.query.filter(
        db.or_(
            Entity.user_id == user.id,
            Entity.is_public == True,
            Entity.shared_with.contains([user.id])
        )
    ).all()

    current_day = now.strftime('%A').lower()
    current_hour = now.hour

    scored = []
    for entity in entities:
        if entity.rating is not None and entity.rating <= 1:
            continue  # matches the existing "Open Now" widget's own filtering

        # Hard proximity cutoff (not a scoring signal) -- per explicit
        # product decision, see docs/entity-geolocation.md. Only applies
        # when both sides have resolved coordinates; an entity or user
        # without them isn't excluded on that basis alone, since "we don't
        # know" isn't the same claim as "too far away."
        distance_miles = None
        if (user.latitude is not None and user.longitude is not None
                and entity.latitude is not None and entity.longitude is not None):
            distance_miles = haversine_miles(user.latitude, user.longitude, entity.latitude, entity.longitude)
            if distance_miles > nearby_distance_miles:
                continue

        is_open = _is_entity_open(entity, current_day, current_hour)
        rating_score = (entity.rating or 2) / 4.0
        score = 0.5 * rating_score
        reason_bits = []

        if is_open:
            score += 0.3
            reason_bits.append(_('open now'))
        if distance_miles is not None:
            reason_bits.append(_('{0:.1f} mi away').format(distance_miles))
        if not entity.visited:
            score += 0.2
            reason_bits.append(_("you haven't visited yet"))
        if entity.rating is not None and entity.rating >= 3:
            reason_bits.append(_('highly rated'))
        if entity.category and entity.category in favorites:
            score += 0.15
            reason_bits.append(_('a favorite category'))

        if score <= 0:
            continue

        scored.append({
            'item_type': 'entity',
            'source_id': entity.id,
            'title': entity.name,
            'reason': ', '.join(reason_bits) if reason_bits else _('Suggested place'),
            'score': score,
        })

    # Deliberately NOT truncated to a top-N here, even though only a handful
    # ever get shown (the API caps at MAX_QUEUE_ITEMS_RETURNED). Every entity
    # that passes the qualification filters above is a genuinely valid
    # candidate; refresh_queue_for_user treats "not in this cycle's
    # candidate set" as "no longer qualifies, prune it" -- truncating here
    # would make a previously-dismissed low-score entity get silently wiped
    # (and its dismissal forgotten) the moment a handful of other entities
    # outscored it, purely from ranking churn rather than the entity itself
    # actually becoming invalid.
    scored.sort(key=lambda c: c['score'], reverse=True)
    return scored


def _event_candidates(user, now):
    events = integration_service.get_calendar_events(
        start_date=now, end_date=now + timedelta(days=EVENT_LOOKAHEAD_DAYS), user=user
    )

    candidates = []
    for event in events:
        if not event.get('id') or not event.get('start_time'):
            continue
        event_date = datetime.strptime(event['start_time'], '%Y-%m-%d %H:%M')
        days_until = max((event_date - now).total_seconds() / 86400.0, 0.0)
        score = max(0.0, 1.0 - (days_until / EVENT_LOOKAHEAD_DAYS))

        if days_until < 1:
            reason = _('Today')
        else:
            reason = _('Coming up in {0} days').format(int(days_until) + 1)

        candidates.append({
            'item_type': 'event',
            'source_id': event['id'],
            'title': event['title'],
            'reason': reason,
            'score': score,
            'event_date': event_date,  # internal-only, read by planning_agent_service
        })
    return candidates


def _task_candidates(user, now):
    """Mustermeister-derived task candidates -- reads MustermeisterTaskCache
    only (see refresh_mustermeister_tasks), never Mustermeister live."""
    if not _task_email_integration_enabled_for(user):
        return []

    today = now.date()
    tasks = MustermeisterTaskCache.query.all()

    candidates = []
    for task in tasks:
        priority_weight = TASK_PRIORITY_WEIGHTS.get(task.priority, 2) / 4.0

        if task.due_date is None:
            proximity_score = 0.0
        else:
            days_until = (task.due_date - today).days
            proximity_score = 1.0 if days_until <= 0 else max(0.0, 1.0 - (days_until / TASK_DUE_LOOKAHEAD_DAYS))

        score = 0.6 * priority_weight + 0.4 * proximity_score

        reason_bits = []
        if task.due_date is None:
            reason_bits.append(_('No due date'))
        elif task.due_date < today:
            reason_bits.append(_('Overdue by {0} days').format((today - task.due_date).days))
            score += 0.15
        elif task.due_date == today:
            reason_bits.append(_('Due today'))
            score += 0.1
        else:
            reason_bits.append(_('Due in {0} days').format((task.due_date - today).days))

        if task.priority == 'high':
            reason_bits.append(_('high priority'))
            score += 0.1
        if task.project:
            reason_bits.append(task.project)

        candidates.append({
            'item_type': 'task',
            'source_id': task.id,
            'title': task.title,
            'reason': ', '.join(reason_bits),
            'score': score,
            # internal-only, read by planning_agent_service:
            'due_date': task.due_date,
            'priority': task.priority,
        })
    return candidates


def _email_candidates(user, now):
    """BriefKorb-derived unread-mail candidates -- reads
    BriefKorbMessageCache only (see refresh_briefkorb_messages), never
    BriefKorb live. 'low-impact' senders are excluded up front;
    'unclassified' senders are kept -- a first-time or irregular sender can
    still be genuinely important, the classifier just hasn't built a
    pattern on them yet."""
    if not _task_email_integration_enabled_for(user):
        return []

    buckets = BriefKorbMessageCache.query.filter(BriefKorbMessageCache.impact != 'low-impact').all()

    candidates = []
    for bucket in buckets:
        tier_weight = EMAIL_IMPACT_TIER_WEIGHTS.get(bucket.impact, 0.5)
        # genericInferenceScore's exact range isn't confirmed against
        # BriefKorb's source -- clamped defensively rather than assumed.
        impact_score = max(0.0, min(1.0, bucket.impact_score)) if bucket.impact_score is not None else 0.5

        hours_since = max((now - bucket.last_received_at).total_seconds() / 3600.0, 0.0)
        recency_score = max(0.0, 1.0 - (hours_since / (EMAIL_RECENCY_WINDOW_DAYS * 24)))

        score = 0.5 * tier_weight + 0.3 * impact_score + 0.2 * recency_score

        reason_bits = []
        if bucket.impact == 'high-impact':
            reason_bits.append(_('high-impact sender'))
        if bucket.count and bucket.count > 1:
            reason_bits.append(_('{0} messages').format(bucket.count))
            score += 0.1
        reason_bits.append(bucket.sender_name or bucket.sender_address)

        candidates.append({
            'item_type': 'email',
            'source_id': bucket.id,
            'title': bucket.subject or bucket.sender_name or bucket.sender_address,
            'reason': ', '.join(reason_bits),
            'score': score,
            # internal-only, read by planning_agent_service:
            'impact': bucket.impact,
            'sender_name': bucket.sender_name,
            'count': bucket.count,
            'last_received_at': bucket.last_received_at,
        })
    return candidates


def _plan_candidates(user, now, candidates):
    """LLM-synthesized 'plan' candidates -- see planning_agent_service.py.
    Takes the already-gathered activity/entity/event/task/email candidates
    (including their internal-only extra fields, e.g. due_date/scheduled_time)
    as input rather than re-querying, and the currently active schedule
    category, which planning_agent_service has no independent way to
    resolve (SchedulesManager needs a request/background-job-scoped user,
    not something it can look up on its own)."""
    from .planning_agent_service import gather_plan_candidates
    active_category = _active_schedule_category(user, now)
    return gather_plan_candidates(user, now, candidates, active_schedule_category=active_category)


def refresh_queue_for_user(user, now=None):
    """Upsert this user's SuggestionQueueItem rows from freshly-gathered
    candidates, preserving dismissed/snoozed status, auto-expiring passed
    snoozes, and dropping rows whose underlying source no longer qualifies
    (deleted/completed/no-longer-viewable) regardless of their status --
    the mechanism that keeps this table from growing without bound."""
    now = now or datetime.utcnow()
    candidates = gather_candidates_for_user(user, now)
    candidate_keys = set()

    for candidate in candidates:
        key = (candidate['item_type'], candidate['source_id'])
        candidate_keys.add(key)
        existing = SuggestionQueueItem.query.filter_by(
            user_id=user.id, item_type=candidate['item_type'], source_id=candidate['source_id']
        ).first()
        if existing:
            existing.title = candidate['title']
            existing.reason = candidate['reason']
            existing.score = candidate['score']
            # status/snoozed_until deliberately left untouched here.
        else:
            db.session.add(SuggestionQueueItem(
                user_id=user.id,
                item_type=candidate['item_type'],
                source_id=candidate['source_id'],
                title=candidate['title'],
                reason=candidate['reason'],
                score=candidate['score'],
                status='pending',
            ))

    expired_snoozes = SuggestionQueueItem.query.filter(
        SuggestionQueueItem.user_id == user.id,
        SuggestionQueueItem.status == 'snoozed',
        SuggestionQueueItem.snoozed_until <= now,
    ).all()
    for item in expired_snoozes:
        item.status = 'pending'
        item.snoozed_until = None

    for item in SuggestionQueueItem.query.filter_by(user_id=user.id).all():
        if (item.item_type, item.source_id) not in candidate_keys:
            db.session.delete(item)

    db.session.commit()
