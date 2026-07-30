from calendar import monthrange
from datetime import datetime

from ..models import EventCache, db
from .custom_calendar_service import expand_entries_for_year
from ..utils.translations import _

VALID_ENTRY_TYPES = ('closure', 'special_hours', 'event', 'other')
VALID_RECURRENCES = ('once', 'annual')
ENTITY_CALENDAR_SOURCE = 'Entity Calendar'
MAX_ENTRIES_PER_ENTITY = 100


class EntityCalendarValidationError(ValueError):
    """Raised when input for an entity calendar entry fails validation.
    The message is written to be shown directly to the user (via _())."""
    pass


def validate_entry_input(data):
    """Validate raw form/JSON input for a new or updated entity calendar
    entry, returning a normalized dict ready to store on
    Entity.calendar_entries (still missing 'id', which the caller assigns).
    """
    title = data.get('title')
    if not isinstance(title, str) or not title.strip():
        raise EntityCalendarValidationError(_("'title' is required and must be a non-empty string."))
    title = title.strip()

    entry_type = data.get('entry_type') or 'other'
    if entry_type not in VALID_ENTRY_TYPES:
        raise EntityCalendarValidationError(
            _("'entry_type' must be one of {0}.").format(VALID_ENTRY_TYPES)
        )

    recurrence = data.get('recurrence')
    if recurrence not in VALID_RECURRENCES:
        raise EntityCalendarValidationError(
            _("'recurrence' must be one of {0}.").format(VALID_RECURRENCES)
        )

    description = data.get('description')
    if description is not None and not isinstance(description, str):
        raise EntityCalendarValidationError(_("'description' must be a string."))

    time = data.get('time')
    if time is not None:
        try:
            time = datetime.strptime(time, '%H:%M').strftime('%H:%M')
        except (TypeError, ValueError):
            raise EntityCalendarValidationError(_("'time' must be in HH:MM 24-hour format."))

    end_time = data.get('end_time')
    if end_time is not None:
        try:
            end_time = datetime.strptime(end_time, '%H:%M').strftime('%H:%M')
        except (TypeError, ValueError):
            raise EntityCalendarValidationError(_("'end_time' must be in HH:MM 24-hour format."))

    end_date = data.get('end_date')
    if end_date is not None:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date().isoformat()
        except (TypeError, ValueError):
            raise EntityCalendarValidationError(_("'end_date' must be an ISO date (YYYY-MM-DD)."))

    entry = {
        'title': title,
        'entry_type': entry_type,
        'recurrence': recurrence,
        'description': description or None,
        'time': time,
        'end_time': end_time,
        'end_date': end_date,
        'date': None,
        'month': None,
        'day': None,
    }

    if recurrence == 'once':
        raw_date = data.get('date')
        try:
            parsed_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            raise EntityCalendarValidationError(_("'date' must be an ISO date (YYYY-MM-DD)."))
        entry['date'] = parsed_date.isoformat()
    else:
        month = data.get('month')
        if isinstance(month, bool) or not isinstance(month, int) or not (1 <= month <= 12):
            raise EntityCalendarValidationError(_("'month' must be an integer between 1 and 12."))
        day = data.get('day')
        # 2000 is a leap year, so this allows Feb 29 -- expand_entries_for_year
        # falls back to Feb 28 in non-leap years.
        max_day = monthrange(2000, month)[1]
        if isinstance(day, bool) or not isinstance(day, int) or not (1 <= day <= max_day):
            raise EntityCalendarValidationError(_("'day' must be a valid day for month {0}.").format(month))
        entry['month'] = month
        entry['day'] = day

    return entry


def _to_expansion_entry(stored_entry):
    """Convert a stored Entity.calendar_entries dict into the normalized
    shape expand_entries_for_year() expects."""
    if stored_entry['recurrence'] == 'once':
        parsed_date = datetime.strptime(stored_entry['date'], '%Y-%m-%d').date()
        return {
            'title': stored_entry['title'],
            'recurrence': 'once',
            'month': parsed_date.month,
            'day': parsed_date.day,
            'year': parsed_date.year,
            'description': stored_entry['description'],
        }
    return {
        'title': stored_entry['title'],
        'recurrence': 'annual',
        'month': stored_entry['month'],
        'day': stored_entry['day'],
        'year': None,
        'description': stored_entry['description'],
    }


def regenerate_event_cache_for_entity(entity, years):
    """Delete and recreate an entity's Entity-Calendar EventCache rows for
    the given years, from its current calendar_entries. Shared by the
    synchronous on-save path and the periodic background refresh."""
    expansion_entries = [_to_expansion_entry(e) for e in entity.get_calendar_entries()]

    for year in years:
        EventCache.query.filter_by(entity_id=entity.id, source=ENTITY_CALENDAR_SOURCE, year=year).delete()
        for occurrence in expand_entries_for_year(expansion_entries, year):
            db.session.add(EventCache(
                title=occurrence['title'],
                date=occurrence['date'],
                description=occurrence['description'],
                source=ENTITY_CALENDAR_SOURCE,
                year=year,
                entity_id=entity.id,
            ))
    db.session.commit()


def delete_event_cache_for_entity(entity_id):
    """Remove all of an entity's Entity Calendar EventCache rows, across all years."""
    EventCache.query.filter_by(entity_id=entity_id, source=ENTITY_CALENDAR_SOURCE).delete()
    db.session.commit()
