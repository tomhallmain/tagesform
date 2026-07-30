"""Candidate-gathering and scoring for the suggestion queue.

Draws on the calendar/entity work built up over this project: activities,
entities (rating/open-now, independently recomputed here rather than via
entities.py's request-scoped lru_cache helpers), and IntegrationService.
get_calendar_events -- which by now already merges public holidays, Hebrew/
USNO/Nobel Prize/rocket-launch events, a user's own custom calendar, and any
entity's calendar entries the user can see, so reusing it here means the
suggestion queue automatically benefits from all of that instead of
re-deriving its own narrower view of "what events exist."

item_type is intentionally open-ended (see SuggestionQueueItem's docstring):
two more candidate sources are planned -- an email application and a task
manager application, both external systems holding their own copies of the
user's data. Nothing here assumes only these three types exist; adding
'email'/'task' later is a matter of adding a new _*_candidates function and
an entry in refresh_queue_for_user's candidate list, not a schema change.
"""

from datetime import datetime, timedelta

from ..models import Activity, Entity, SuggestionQueueItem, db
from .integration_service import integration_service
from .schedules_manager import SchedulesManager
from ..utils.translations import _

ACTIVITY_LOOKAHEAD_DAYS = 14
EVENT_LOOKAHEAD_DAYS = 14


def gather_candidates_for_user(user, now=None):
    """Returns a list of dicts: {item_type, source_id, title, reason, score}."""
    now = now or datetime.utcnow()
    candidates = []
    candidates.extend(_activity_candidates(user, now))
    candidates.extend(_entity_candidates(user, now))
    candidates.extend(_event_candidates(user, now))
    return candidates


def _favorite_categories(user):
    """User.preferences doesn't currently have a 'favorite categories' field
    -- nothing in settings.py writes one. Checking for it anyway costs
    nothing (a plain dict .get on JSON that may not have the key) and means
    this signal activates automatically if such a preference is ever added,
    rather than needing this scoring code to change too."""
    preferences = user.preferences or {}
    favorites = preferences.get('favorite_categories')
    return set(favorites) if favorites else set()


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

        is_open = _is_entity_open(entity, current_day, current_hour)
        rating_score = (entity.rating or 2) / 4.0
        score = 0.5 * rating_score
        reason_bits = []

        if is_open:
            score += 0.3
            reason_bits.append(_('open now'))
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
        })
    return candidates


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
