from calendar import isleap, monthrange
from datetime import date, datetime

import yaml

from ..models import EventCache, db
from ..utils.translations import _

MAX_ENTRIES = 200
MAX_RAW_YAML_BYTES = 64 * 1024
CUSTOM_CALENDAR_SOURCE = 'Custom Calendar'
VALID_RECURRENCES = ('once', 'annual')


class DescriptorValidationError(ValueError):
    """Raised when a user's calendar descriptor YAML fails validation --
    either malformed YAML syntax or a schema violation. The message is
    written to be shown directly to the user (via _()), identifying which
    entry and field failed."""
    pass


def parse_descriptor(raw_yaml):
    """Parse and validate a user's calendar descriptor YAML into a list of
    normalized entry dicts.

    Uses yaml.safe_load exclusively -- never yaml.load/FullLoader/UnsafeLoader.
    This is fully untrusted, user-supplied content, and unsafe PyYAML loading
    can deserialize arbitrary Python objects via tags like !!python/object.
    """
    if raw_yaml is None or not raw_yaml.strip():
        raise DescriptorValidationError(_('Calendar descriptor is empty.'))

    if len(raw_yaml.encode('utf-8')) > MAX_RAW_YAML_BYTES:
        raise DescriptorValidationError(
            _('Calendar descriptor is too large (max {0} KB).').format(MAX_RAW_YAML_BYTES // 1024)
        )

    try:
        parsed = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as e:
        raise DescriptorValidationError(_('Invalid YAML syntax: {0}').format(e))

    if not isinstance(parsed, dict) or 'events' not in parsed:
        raise DescriptorValidationError(_("Descriptor must be a mapping with a top-level 'events' list."))

    raw_entries = parsed['events']
    if not isinstance(raw_entries, list):
        raise DescriptorValidationError(_("'events' must be a list."))

    if len(raw_entries) > MAX_ENTRIES:
        raise DescriptorValidationError(_('Too many entries (max {0}).').format(MAX_ENTRIES))

    return [_validate_entry(raw_entry, index) for index, raw_entry in enumerate(raw_entries)]


def _validate_entry(raw_entry, index):
    label = _('Entry {0}').format(index + 1)
    if not isinstance(raw_entry, dict):
        raise DescriptorValidationError(_('{0} must be a mapping.').format(label))

    title = raw_entry.get('title')
    if not isinstance(title, str) or not title.strip():
        raise DescriptorValidationError(
            _("{0}: 'title' is required and must be a non-empty string.").format(label)
        )
    title = title.strip()

    recurrence = raw_entry.get('recurrence')
    if recurrence not in VALID_RECURRENCES:
        raise DescriptorValidationError(
            _("{0} ('{1}'): 'recurrence' must be one of {2}.").format(label, title, VALID_RECURRENCES)
        )

    description = raw_entry.get('description')
    if description is not None and not isinstance(description, str):
        raise DescriptorValidationError(_("{0} ('{1}'): 'description' must be a string.").format(label, title))

    location = raw_entry.get('location')
    if location is not None and not isinstance(location, str):
        raise DescriptorValidationError(_("{0} ('{1}'): 'location' must be a string.").format(label, title))

    entry = {
        'title': title,
        'recurrence': recurrence,
        'description': description,
        'location': location,
    }

    if recurrence == 'once':
        parsed_date = _parse_once_date(raw_entry.get('date'), label, title)
        entry['month'] = parsed_date.month
        entry['day'] = parsed_date.day
        entry['year'] = parsed_date.year
    else:  # annual
        month = raw_entry.get('month')
        if isinstance(month, bool) or not isinstance(month, int) or not (1 <= month <= 12):
            raise DescriptorValidationError(
                _("{0} ('{1}'): 'month' must be an integer between 1 and 12.").format(label, title)
            )
        day = raw_entry.get('day')
        # 2000 is a leap year, so this allows Feb 29 -- annual expansion falls
        # back to Feb 28 in non-leap years, see expand_entries_for_year.
        max_day = monthrange(2000, month)[1]
        if isinstance(day, bool) or not isinstance(day, int) or not (1 <= day <= max_day):
            raise DescriptorValidationError(
                _("{0} ('{1}'): 'day' must be a valid day for month {2}.").format(label, title, month)
            )
        entry['month'] = month
        entry['day'] = day
        entry['year'] = None

    return entry


def _parse_once_date(raw_date, label, title):
    if isinstance(raw_date, datetime):
        return raw_date.date()
    if isinstance(raw_date, date):
        return raw_date
    if isinstance(raw_date, str):
        try:
            return datetime.strptime(raw_date, '%Y-%m-%d').date()
        except ValueError:
            pass
    raise DescriptorValidationError(
        _("{0} ('{1}'): 'once' entries require a 'date' in ISO format (YYYY-MM-DD).").format(label, title)
    )


def expand_entries_for_year(entries, year):
    """Expand normalized entries (from parse_descriptor, or any other caller
    producing the same {title, recurrence, month, day, year, description}
    shape -- e.g. entity_calendar_service.py) into concrete occurrences
    falling in `year`.

    'once' entries appear only in their own year. 'annual' entries recur
    every year; a Feb 29 annual entry falls back to Feb 28 in non-leap years.
    """
    occurrences = []
    for entry in entries:
        if entry['recurrence'] == 'once':
            if entry['year'] != year:
                continue
            month, day = entry['month'], entry['day']
        else:
            month, day = entry['month'], entry['day']
            if month == 2 and day == 29 and not isleap(year):
                day = 28

        occurrences.append({
            'title': entry['title'],
            'date': datetime(year, month, day),
            'description': entry['description'],
            'location': entry.get('location'),
        })

    return occurrences


def regenerate_event_cache_for_user(user_id, entries, years):
    """Delete and recreate a user's Custom Calendar EventCache rows for the
    given years, from already-parsed entries. Shared by the synchronous
    on-save path and the periodic background refresh so both stay in sync."""
    for year in years:
        EventCache.query.filter_by(user_id=user_id, source=CUSTOM_CALENDAR_SOURCE, year=year).delete()
        for occurrence in expand_entries_for_year(entries, year):
            db.session.add(EventCache(
                title=occurrence['title'],
                date=occurrence['date'],
                description=occurrence['description'],
                location=occurrence['location'],
                source=CUSTOM_CALENDAR_SOURCE,
                year=year,
                user_id=user_id,
            ))
    db.session.commit()


def delete_event_cache_for_user(user_id):
    """Remove all of a user's Custom Calendar EventCache rows, across all years."""
    EventCache.query.filter_by(user_id=user_id, source=CUSTOM_CALENDAR_SOURCE).delete()
    db.session.commit()
