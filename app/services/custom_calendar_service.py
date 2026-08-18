from calendar import isleap, monthrange
from datetime import date, datetime, timedelta

import yaml

from ..models import EventCache, db
from ..utils.translations import _

MAX_ENTRIES = 200
MAX_RAW_YAML_BYTES = 64 * 1024
CUSTOM_CALENDAR_SOURCE = 'Custom Calendar'
# 'nth_weekday'/'periodic_years'/'seasonal' are for events that recur every
# year (or every N years) in roughly the same part of the year without a
# single fixed month/day -- see expand_entries_for_year and the per-kind
# validators below. Shared with entity_calendar_service.py, which imports
# this tuple and the composite validators rather than redefining them.
VALID_RECURRENCES = ('once', 'annual', 'nth_weekday', 'periodic_years', 'seasonal')


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

    prefix = _("{0} ('{1}'): ").format(label, title)

    if recurrence == 'once':
        parsed_date = _parse_once_date(raw_entry.get('date'), label, title)
        entry['month'] = parsed_date.month
        entry['day'] = parsed_date.day
        entry['year'] = parsed_date.year
    elif recurrence == 'annual':
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
    elif recurrence == 'nth_weekday':
        entry.update(_validate_nth_weekday_fields(raw_entry, prefix, DescriptorValidationError))
        entry['year'] = None
    elif recurrence == 'periodic_years':
        entry.update(_validate_periodic_years_fields(raw_entry, prefix, DescriptorValidationError))
        entry['year'] = None
    else:  # seasonal
        entry.update(_validate_seasonal_fields(raw_entry, prefix, DescriptorValidationError))
        entry['year'] = None

    return entry


def _validate_month_field(value, prefix, error_cls):
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 12):
        raise error_cls(_("{0}'month' must be an integer between 1 and 12.").format(prefix))
    return value


def _validate_weekday_field(value, prefix, error_cls):
    if isinstance(value, bool) or not isinstance(value, int) or not (0 <= value <= 6):
        raise error_cls(_("{0}'weekday' must be an integer between 0 (Monday) and 6 (Sunday).").format(prefix))
    return value


def _validate_ordinal_field(value, prefix, error_cls):
    if isinstance(value, bool) or not isinstance(value, int) or value not in (1, 2, 3, 4, 5, -1):
        raise error_cls(_("{0}'ordinal' must be 1-5, or -1 for the last occurrence in the month.").format(prefix))
    return value


def _validate_day_field(value, month, prefix, error_cls):
    max_day = monthrange(2000, month)[1]
    if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= max_day):
        raise error_cls(_("{0}'day' must be a valid day for month {1}.").format(prefix, month))
    return value


def _validate_nth_weekday_fields(raw_entry, prefix, error_cls):
    """month + the ordinal-th weekday in that month, e.g. 'first Saturday
    in May' -- see _nth_weekday_date. Shared between 'nth_weekday' entries
    and the weekday-based form of 'periodic_years'."""
    month = _validate_month_field(raw_entry.get('month'), prefix, error_cls)
    weekday = _validate_weekday_field(raw_entry.get('weekday'), prefix, error_cls)
    ordinal = _validate_ordinal_field(raw_entry.get('ordinal'), prefix, error_cls)
    return {'month': month, 'weekday': weekday, 'ordinal': ordinal, 'day': None,
            'interval_years': None, 'anchor_year': None}


def _validate_periodic_years_fields(raw_entry, prefix, error_cls):
    """Every `interval_years` years counting from `anchor_year`, combined
    with either a fixed (month, day) or a (month, weekday, ordinal) --
    covers cadences like 'every 4 years' (Olympics-style)."""
    interval_years = raw_entry.get('interval_years')
    if isinstance(interval_years, bool) or not isinstance(interval_years, int) or interval_years < 2:
        raise error_cls(_("{0}'interval_years' must be an integer >= 2.").format(prefix))

    anchor_year = raw_entry.get('anchor_year')
    if isinstance(anchor_year, bool) or not isinstance(anchor_year, int) or anchor_year < 1:
        raise error_cls(_("{0}'anchor_year' must be a positive integer.").format(prefix))

    has_day = raw_entry.get('day') is not None
    has_weekday_ordinal = raw_entry.get('weekday') is not None or raw_entry.get('ordinal') is not None
    if has_day and has_weekday_ordinal:
        raise error_cls(
            _("{0}'periodic_years' entries must specify either 'day' or 'weekday'+'ordinal', not both.").format(prefix)
        )
    if has_day:
        month = _validate_month_field(raw_entry.get('month'), prefix, error_cls)
        day = _validate_day_field(raw_entry.get('day'), month, prefix, error_cls)
        return {'interval_years': interval_years, 'anchor_year': anchor_year,
                'month': month, 'day': day, 'weekday': None, 'ordinal': None}
    if has_weekday_ordinal:
        fields = _validate_nth_weekday_fields(raw_entry, prefix, error_cls)
        return {'interval_years': interval_years, 'anchor_year': anchor_year,
                'month': fields['month'], 'day': None,
                'weekday': fields['weekday'], 'ordinal': fields['ordinal']}
    raise error_cls(_("{0}'periodic_years' entries require either 'day' or 'weekday'+'ordinal'.").format(prefix))


def _validate_seasonal_fields(raw_entry, prefix, error_cls):
    """month, with an optional day (defaults to the 1st) -- for events with
    no fixed date rule at all. expand_entries_for_year flags the resulting
    occurrence's description as approximate rather than treating this day
    as a real, confirmed date."""
    month = _validate_month_field(raw_entry.get('month'), prefix, error_cls)
    raw_day = raw_entry.get('day')
    day = 1 if raw_day is None else _validate_day_field(raw_day, month, prefix, error_cls)
    return {'month': month, 'day': day, 'weekday': None, 'ordinal': None,
            'interval_years': None, 'anchor_year': None}


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


def _nth_weekday_date(year, month, weekday, ordinal):
    """Date of the `ordinal`-th `weekday` in `month`/`year`, or None if that
    occurrence doesn't exist (only possible for ordinal=5 -- every month has
    at least 4 of each weekday, but not always a 5th). ordinal=-1 means "the
    last occurrence in the month," which always exists. weekday matches
    date.weekday() (0=Monday..6=Sunday)."""
    days_in_month = monthrange(year, month)[1]
    if ordinal == -1:
        last_date = date(year, month, days_in_month)
        offset = (last_date.weekday() - weekday) % 7
        return last_date - timedelta(days=offset)

    first_date = date(year, month, 1)
    offset = (weekday - first_date.weekday()) % 7
    day = 1 + offset + (ordinal - 1) * 7
    if day > days_in_month:
        return None
    return date(year, month, day)


def expand_entries_for_year(entries, year):
    """Expand normalized entries (from parse_descriptor, or any other caller
    producing the same {title, recurrence, month, day, year, description,
    weekday, ordinal, interval_years, anchor_year} shape -- e.g.
    entity_calendar_service.py) into concrete occurrences falling in `year`.

    'once' entries appear only in their own year. 'annual' entries recur
    every year; a Feb 29 annual entry falls back to Feb 28 in non-leap years.
    'nth_weekday' entries (e.g. 'first Saturday in May') are skipped for a
    given year if that ordinal occurrence doesn't exist (see
    _nth_weekday_date). 'periodic_years' entries are skipped for any year
    that isn't `interval_years` years past `anchor_year`, then resolve like
    'annual' or 'nth_weekday' depending on which fields they carry.
    'seasonal' entries have no real day -- every year gets one occurrence at
    (month, day or 1), with the description flagged as approximate.
    """
    occurrences = []
    for entry in entries:
        recurrence = entry['recurrence']
        description = entry['description']

        if recurrence == 'once':
            if entry['year'] != year:
                continue
            month, day = entry['month'], entry['day']

        elif recurrence == 'annual':
            month, day = entry['month'], entry['day']
            if month == 2 and day == 29 and not isleap(year):
                day = 28

        elif recurrence == 'nth_weekday':
            occurrence_date = _nth_weekday_date(year, entry['month'], entry['weekday'], entry['ordinal'])
            if occurrence_date is None:
                continue
            month, day = occurrence_date.month, occurrence_date.day

        elif recurrence == 'periodic_years':
            if (year - entry['anchor_year']) % entry['interval_years'] != 0:
                continue
            if entry.get('day') is not None:
                month, day = entry['month'], entry['day']
                if month == 2 and day == 29 and not isleap(year):
                    day = 28
            else:
                occurrence_date = _nth_weekday_date(year, entry['month'], entry['weekday'], entry['ordinal'])
                if occurrence_date is None:
                    continue
                month, day = occurrence_date.month, occurrence_date.day

        else:  # seasonal
            # entry.get('day') rather than entry['day'] -- _validate_seasonal_fields
            # already defaults an omitted day to 1, but this is also reached by
            # callers that build entries directly from trusted, non-validated
            # data (e.g. default_event_service.py's DB-seeded catalog rows),
            # so the default needs to hold here too, not only in the validator.
            month, day = entry['month'], entry.get('day') or 1
            marker = _('(approximate -- exact date announced separately each year)')
            description = f'{description} {marker}' if description else marker

        occurrences.append({
            'title': entry['title'],
            'date': datetime(year, month, day),
            'description': description,
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
