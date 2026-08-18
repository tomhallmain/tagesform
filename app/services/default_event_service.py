from ..models import DefaultEventDescriptor, EventCache, db
from .custom_calendar_service import expand_entries_for_year

DEFAULT_EVENT_SOURCE = 'Default Event'


def _to_expansion_entry(descriptor):
    """Convert a DefaultEventDescriptor row into the normalized shape
    expand_entries_for_year() expects, reading whichever fields its
    recurrence kind needs out of recurrence_params."""
    params = descriptor.recurrence_params or {}
    return {
        'title': descriptor.title,
        'recurrence': descriptor.recurrence,
        'month': params.get('month'),
        'day': params.get('day'),
        'weekday': params.get('weekday'),
        'ordinal': params.get('ordinal'),
        'interval_years': params.get('interval_years'),
        'anchor_year': params.get('anchor_year'),
        'year': params.get('year'),
        'description': descriptor.description,
        'location': descriptor.location,
    }


def regenerate_event_cache_for_user_default_events(user_id, subscribed_ids, years):
    """Delete and recreate a user's Default Event EventCache rows for the
    given years, from whichever catalog rows in `subscribed_ids` still
    exist. Shared by the synchronous on-save path and the periodic
    background refresh, same pattern as regenerate_event_cache_for_user/
    regenerate_event_cache_for_entity.

    Called with an empty `subscribed_ids` (e.g. a user who unsubscribed
    from everything) still deletes any stale rows for `years` and inserts
    nothing -- there's no separate delete-only function for that reason.
    """
    descriptors = (
        DefaultEventDescriptor.query.filter(DefaultEventDescriptor.id.in_(subscribed_ids)).all()
        if subscribed_ids else []
    )
    entries = [_to_expansion_entry(d) for d in descriptors]

    for year in years:
        EventCache.query.filter_by(user_id=user_id, source=DEFAULT_EVENT_SOURCE, year=year).delete()
        for occurrence in expand_entries_for_year(entries, year):
            db.session.add(EventCache(
                title=occurrence['title'],
                date=occurrence['date'],
                description=occurrence['description'],
                location=occurrence['location'],
                source=DEFAULT_EVENT_SOURCE,
                year=year,
                user_id=user_id,
            ))
    db.session.commit()
