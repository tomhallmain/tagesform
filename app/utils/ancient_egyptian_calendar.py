"""Gregorian <-> Ancient Egyptian civil-calendar conversion.

The ancient Egyptian civil calendar was 365 days: 12 months of 30 days each,
grouped into 3 seasons of 4 months, plus 5 extra "epagomenal" days that
belonged to no month or season. Unlike its direct descendant the Coptic
calendar (which added a leap day every 4 years), the ancient civil calendar
was never corrected for the solar year drifting relative to it -- that drift
is expected and intentional here, not a bug.

Egyptology has no single agreed-upon epoch for aligning this calendar to the
Gregorian calendar (the real one drifted through the seasons continuously
across millennia of use, and was itself reset/reinterpreted differently in
different eras). Rather than assert a specific historical epoch as fact,
this implementation anchors 1 Thoth (the ancient New Year) to September 11 in
a recent reference year -- the same Gregorian date the Coptic calendar's own
New Year (Nayrouz) usually falls on, since Coptic directly continues this
calendar's month/day structure. This is a deliberate, documented convention
for this feature, not a claim of precise historical reconstruction. No year
number is computed or displayed for the same reason -- only season, month,
and day (or epagomenal day) are well-defined without picking a contested epoch.
"""

from datetime import date, datetime

MONTH_NAMES = [
    'Thoth', 'Phaophi', 'Athyr', 'Choiak',
    'Tybi', 'Mechir', 'Phamenoth', 'Pharmuthi',
    'Pachons', 'Payni', 'Epiphi', 'Mesore',
]

SEASON_NAMES = ['Akhet', 'Peret', 'Shemu']  # Inundation, Growth, Harvest

DAYS_PER_MONTH = 30
MONTHS_PER_SEASON = 4
MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = MONTHS_PER_YEAR * DAYS_PER_MONTH  # 360, before epagomenal days
EPAGOMENAL_DAYS = 5
CYCLE_LENGTH = DAYS_PER_YEAR + EPAGOMENAL_DAYS  # 365

# Reference alignment -- see module docstring. Arbitrary but documented.
EPOCH = date(2024, 9, 11)  # 1 Thoth


def to_ancient_egyptian_date(gregorian_date):
    """Convert a Gregorian date (date or datetime) to its Ancient Egyptian
    civil-calendar equivalent.

    Returns a dict: {'season': str|None, 'month': str|None, 'day': int,
    'is_epagomenal': bool}. `season`/`month` are None for epagomenal days,
    which belong to no month or season.
    """
    if isinstance(gregorian_date, datetime):
        gregorian_date = gregorian_date.date()

    days_since_epoch = (gregorian_date - EPOCH).days
    day_in_cycle = days_since_epoch % CYCLE_LENGTH  # 0..364

    if day_in_cycle < DAYS_PER_YEAR:
        month_index = day_in_cycle // DAYS_PER_MONTH
        day_of_month = day_in_cycle % DAYS_PER_MONTH + 1
        season_index = month_index // MONTHS_PER_SEASON
        return {
            'season': SEASON_NAMES[season_index],
            'month': MONTH_NAMES[month_index],
            'day': day_of_month,
            'is_epagomenal': False,
        }

    epagomenal_day = day_in_cycle - DAYS_PER_YEAR + 1  # 1..5
    return {
        'season': None,
        'month': None,
        'day': epagomenal_day,
        'is_epagomenal': True,
    }


def format_ancient_egyptian_date(converted):
    """Render a to_ancient_egyptian_date() result as a short display string."""
    if converted['is_epagomenal']:
        return f"Epagomenal day {converted['day']}"
    return f"{converted['day']} {converted['month']} ({converted['season']})"
