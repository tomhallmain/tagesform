import datetime
import requests
import time

from ..utils.logging_setup import get_logger

logger = get_logger(__name__)

REQUEST_TIMEOUT_SECONDS = 10


class EventGroup:
    def __init__(self, date=datetime.datetime.now(), events=[]):
        self.date = date
        self.events = events
    
    def add_event(self, event):
        self.events.append(event)

    def __eq__(self, other: object):
        return isinstance(other, EventGroup) and self.date == other.date

    def __hash__(self) -> int:
        return hash(self.date)

class Event:
    def __init__(self, name="", date=datetime.datetime.now(), source=None,
                 fixed=False, country=None, other_name=None, notes=None):
        self.name = str(name) if name else ""
        self.date = date
        self.sources = []
        self.fixed = fixed
        self.countries = []
        self.other_names = []
        self.notes = []
        if source is not None:
            if not source in self.sources:
                self.sources.append(source)
        if country is not None:
            if isinstance(country, list):
                self.countries.extend([str(c) for c in country])
            else:
                self.countries.append(str(country))
        if notes is not None:
            if isinstance(notes, list):
                self.notes.extend([str(n) if not isinstance(n, dict) else n for n in notes])
            else:
                self.notes.append(str(notes) if not isinstance(notes, dict) else notes)
        if other_name is not None:
            if not other_name in self.other_names:
                self.other_names.append(str(other_name))

    def merge(self, other):
        if self.fixed is None and other.fixed is not None:
            self.fixed = other.fixed
        for country in other.countries:
            if not country in self.countries:
                self.countries.append(country)
        for note in other.notes:
            if not note in self.notes:
                self.notes.append(note)
        for other_name in other.other_names:
            if not other_name in self.other_names:
                self.other_names.append(other_name)

    def __str__(self):
        sources = ",".join(self.sources)
        date = self.date.strftime("%Y-%m-%d")
        out = f"{self.name} ({date}) from {sources}"
        if len(self.other_names) > 0:
            other_names = ",".join(self.other_names)
            out += f"\n    Other Names: {other_names}"
        if len(self.notes) > 0:
            for note in self.notes:
                if type(note) == dict:
                    for k, v in note.items():
                        out += f"\n    {k} - {v}"
                else:
                    out += f"\n    {note}"
        return out

    @staticmethod
    def from_holiday_api(event):
        notes = []
        if "public" in event:
            notes.append({"public": event["public"]})
        new_event = Event(name=event["name"],
            date=datetime.datetime.strptime(event["date"], "%Y-%m-%d"),
            source="Holiday API",
            fixed=None,
            country=event["country"],
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def from_nager_public_holidays_api(event):
        notes = []
        if "launchYear" in event:
            notes.append({"launchYear": event["launchYear"]})
        new_event = Event(name=event["name"],
            date=datetime.datetime.fromisoformat(event["date"]),
            source="Nager Public Holidays API",
            fixed=event["fixed"],
            country=event["countryCode"],
            other_name=event["localName"],
            notes=notes)
        return new_event

    @staticmethod
    def from_hijri_calendar(event):
        notes = []
        new_event = Event(name=event["name"],
            date=datetime.datetime.strptime(event["date"], "%Y-%m-%d"),
            source="Hijri Calendar",
            fixed=None,
            country="IR",
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def contains_ordinal_str(event_name):
        for s in ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th"]:
            if s in event_name:
                return True
        return False

    @staticmethod
    def get_inadiutorium_event_name(celebrations_list):
        if len(celebrations_list) == 0:
            raise Exception("Could not find name for event - celebrations list: empty celebrations list")

        event_name = celebrations_list[0]["title"]

        if len(celebrations_list) > 1:
            other_name = event_name
            found_other_name = False
            i = 1
            while i < len(celebrations_list):
                other_name = celebrations_list[i]["title"]
                if Event.contains_ordinal_str(other_name):
                    found_other_name = True
                    break
                i += 1
            if found_other_name:
                event_name = other_name

        if event_name is None:
            raise Exception("Could not find name for event - celebrations list: " + str(celebrations_list))

        return event_name

    @staticmethod
    def from_inadiutorium_api(event):
        notes = []
        if "season" in event:
            notes.append({"season": event["season"]})
        if "season_week" in event:
            notes.append({"season_week": event["season_week"]})
        if "celebrations" in event:
            notes.append({"celebrations": event["celebrations"]})
        event_name = Event.get_inadiutorium_event_name(event["celebrations"])
        new_event = Event(name=event_name,
            date=datetime.datetime.fromisoformat(event["date"]),
            source="Inadiutorium API",
            fixed=None,
            country=None,
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def from_hijri_api(event):
        notes = []
        notes.append({"hijri": event["hijri"]})
        event_name = event["hijri"]["holidays"][0]
        new_event = Event(name=event_name,
            date=datetime.datetime.strptime(event["gregorian"]["date"], "%Y-%m-%d"),
            source="Hijri API",
            fixed=False,
            country=None,
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def from_hebcal_api(event):
        notes = []
        if "category" in event:
            notes.append({"category": event["category"]})
        new_event = Event(name=event["title"],
            date=datetime.datetime.fromisoformat(event["date"]),
            source="Hebcal",
            fixed=None,
            country=None,
            other_name=event.get("hebrew"),
            notes=notes)
        return new_event

    @staticmethod
    def from_usno_season_api(item):
        """item shape: {'year', 'month', 'day', 'phenom', 'time'} -- phenom
        is one of 'Equinox', 'Solstice', 'Perihelion', 'Aphelion'."""
        notes = []
        if "time" in item:
            notes.append({"time_utc": item["time"]})
        new_event = Event(name=item["phenom"],
            date=datetime.datetime(item["year"], item["month"], item["day"]),
            source="USNO",
            fixed=True,
            country=None,
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def from_usno_eclipse_api(item):
        """item shape: {'year', 'month', 'day', 'event'} -- event is a
        description like 'Annular Solar Eclipse'."""
        new_event = Event(name=item["event"],
            date=datetime.datetime(item["year"], item["month"], item["day"]),
            source="USNO",
            fixed=True,
            country=None,
            other_name=None,
            notes=None)
        return new_event

    @staticmethod
    def from_usno_moon_phase_api(item):
        """item shape: {'year', 'month', 'day', 'phase', 'time'} -- phase is
        one of 'New Moon', 'First Quarter', 'Full Moon', 'Last Quarter'."""
        notes = []
        if "time" in item:
            notes.append({"time_utc": item["time"]})
        new_event = Event(name=item["phase"],
            date=datetime.datetime(item["year"], item["month"], item["day"]),
            source="USNO",
            fixed=True,
            country=None,
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def from_launch_library_api(item):
        notes = []
        status = item.get("status") or {}
        if status.get("name"):
            notes.append({"status": status["name"]})
        mission = item.get("mission") or {}
        if mission.get("description"):
            notes.append({"mission": mission["description"]})
        # 'net' ("no earlier than") is ISO 8601 with a trailing 'Z'. Stripped
        # to a naive datetime -- every other Event.date in this module is
        # naive, and mixing naive/aware datetimes would raise a TypeError the
        # moment this gets sorted/compared against them in get_events().
        launch_time = datetime.datetime.fromisoformat(item["net"].replace("Z", "+00:00")).replace(tzinfo=None)
        new_event = Event(name=item["name"],
            date=launch_time,
            source="Launch Library",
            fixed=False,
            country=None,
            other_name=None,
            notes=notes)
        return new_event

    @staticmethod
    def merge_events(events=[], events_to_merge=[]):
        for event_to_merge in events_to_merge:
            has_merged_event = False
            for event in events:
                if event_to_merge.name == event.name and event_to_merge.date == event.date:
                    event.merge(event_to_merge)
                    has_merged_event = True
                    break
            if not has_merged_event:
                events.append(event_to_merge)


def format_event(event):
    """Convert an Event into the plain-dict shape used for API responses and
    EventCache rows -- shared by IntegrationService.fetch_live_calendar_events
    and the computed-calendar backfill job so this shape is defined once."""
    return {
        'title': str(event.name) if event.name else 'Untitled Event',
        'start_time': event.date.strftime('%Y-%m-%d %H:%M') if event.date else None,
        'description': str(event.notes[0]) if event.notes else None,
        'location': str(event.countries[0]) if event.countries else None,
        'sources': list(map(str, event.sources)) if event.sources else []
    }


class HolidayAPI:
    BASE_URL = "https://holidayapi.com/v1/holidays"

    def __init__(self, api_key=None):
        self.api_key = api_key

    def __build_url(self, country, year):
        return f"{self.BASE_URL}?key={self.api_key}&country={country}&year={year}"

    def get_events_for_country(self, country="US", year=-1):
        events = []
        try:
            events_json = requests.get(self.__build_url(country, year), timeout=REQUEST_TIMEOUT_SECONDS).json()
            for event in events_json:
                events.append(Event.from_holiday_api(event))
        except Exception as e:
            logger.error("Error getting events from Holiday API: " + str(e))
            raise e
        return events

    def get_events(self, country_codes=["US"], year=-1):
        events = []
        for country in country_codes:
            Event.merge_events(events, self.get_events_for_country(country, year))
        return events



class NagerPublicHolidaysAPI:
    BASE_URL = "https://date.nager.at/api/v3/publicholidays/"

    def __init__(self, api_key=None):
        self.api_key = api_key
    
    def __build_url(self, country_code="US", year=-1):
        return self.BASE_URL + str(year) + "/" + country_code

    def get_events_for_country(self, country_code="US", year=-1):
        events = []
        try:
            events_json = requests.get(self.__build_url(country_code, year), timeout=REQUEST_TIMEOUT_SECONDS).json()
            for event in events_json:
                events.append(Event.from_nager_public_holidays_api(event))
        except Exception as e:
            logger.error("Error getting events from Nager Public Holidays API: " + str(e))
            raise e
        return events

    def get_events(self, country_codes=["US"], year=-1):
        events = []
        for country in country_codes:
            Event.merge_events(events, self.get_events_for_country(country, year))
        return events


class InadiutoriumAPI:
    """Roman Catholic liturgical calendar via the free Inadiutorium API.

    Not wired into CalendarAggregator.get_events() -- same reasoning as
    HebcalAPI/USNOAstronomicalEventsAPI: this calendar is computed from
    fixed rules (the Easter computus plus the standard liturgical calendar
    structure), not live/government-changeable data, so re-fetching it on
    update_event_cache's tight recurring cycle is unnecessary load against
    a slow remote server (~20s per monthly call). Used instead by the
    backfill_computed_calendar_events background job.
    """
    BASE_URL = "http://calapi.inadiutorium.cz/api/v0/en/calendars/default/"

    def __init__(self):
        pass

    def __build_url(self, year=-1, month=-1):
        return self.BASE_URL + str(year) + "/" + str(month)

    def get_events_for_month(self, year=-1, month=-1):
        events = []
        try:
            events_json = requests.get(self.__build_url(year, month), timeout=REQUEST_TIMEOUT_SECONDS).json()
            for event in events_json:
                events.append(Event.from_inadiutorium_api(event))
            time.sleep(0.5)
        except Exception as e:
            logger.error("Error getting events from Inadiutorium API: " + str(e))
            raise e
        return events

    def get_events(self, year=-1):
        events = []
        for month in range(0, 12):
            events.extend(self.get_events_for_month(year, month + 1))        
        return events



class HijriCalendarAPI:
    # Maybe pip install hijri-converter
    BASE_URL = "http://api.aladhan.com/v1/"
    G_TO_H_CALENDAR = "gToHCalendar/"

    def __init__(self) -> None:
        pass

    def __build_url(self, month=-1, year=-1):
        return self.BASE_URL + self.G_TO_H_CALENDAR + str(month) + '/' + str(year)

    def get_events_for_month(self, month=-1, year=-1):
        events = []
        try:
            dates_json  = requests.get(self.__build_url(month, year), timeout=REQUEST_TIMEOUT_SECONDS).json()["data"]
            for date in dates_json:
                if len(date["hijri"]["holidays"]) > 0:
                    events.append(Event.from_hijri_api(date))
        except Exception as e:
            logger.error("Error getting events from Hijri Calendar API: " + str(e))
            raise e
        return events

    def get_events(self, year=-1):
        events = []
        for month in range(0, 12):
            events.extend(self.get_events_for_month(month + 1, year))
        return events


class HebcalAPI:
    """Jewish/Hebrew calendar holidays via the free Hebcal REST API.

    Unlike the other sources in this module, this is NOT wired into
    CalendarAggregator.get_events()/merged with the other three -- Hebrew
    calendar dates come from a fixed, well-defined arithmetic calendar (not
    live/government-changeable data), so re-fetching them on the same
    recurring cadence as Nager would be pure waste against a free,
    unauthenticated public API. It's used instead by the
    backfill_computed_calendar_events background job, which caches a wide
    horizon of years and only re-touches it to extend the tail.
    """
    BASE_URL = "https://www.hebcal.com/hebcal"

    def __init__(self):
        pass

    def __build_url(self, year=-1):
        return f"{self.BASE_URL}?v=1&cfg=json&year={year}&maj=on&min=on&mod=on"

    def get_events(self, year=-1):
        events = []
        try:
            items = requests.get(self.__build_url(year), timeout=REQUEST_TIMEOUT_SECONDS).json().get("items", [])
            for item in items:
                events.append(Event.from_hebcal_api(item))
        except Exception as e:
            logger.error("Error getting events from Hebcal API: " + str(e))
            raise e
        return events


class USNOAstronomicalEventsAPI:
    """Equinoxes/solstices/perihelion/aphelion, solar eclipses, and moon
    phases via the free, keyless US Naval Observatory Astronomical
    Applications API (aa.usno.navy.mil).

    Not wired into CalendarAggregator.get_events() -- same reasoning as
    HebcalAPI: these are computed/deterministic (not live-changing) data,
    so they belong in the backfill_computed_calendar_events job instead.
    """
    BASE_URL = "https://aa.usno.navy.mil/api"

    def __init__(self):
        pass

    def get_events(self, year=-1):
        events = []
        events.extend(self._get_seasons(year))
        events.extend(self._get_solar_eclipses(year))
        events.extend(self._get_moon_phases(year))
        return events

    def _get_seasons(self, year):
        events = []
        try:
            data = requests.get(f"{self.BASE_URL}/seasons", params={"year": year},
                                 timeout=REQUEST_TIMEOUT_SECONDS).json().get("data", [])
            for item in data:
                events.append(Event.from_usno_season_api(item))
        except Exception as e:
            logger.error("Error getting seasons from USNO API: " + str(e))
            raise e
        return events

    def _get_solar_eclipses(self, year):
        events = []
        try:
            eclipses = requests.get(f"{self.BASE_URL}/eclipses/solar/year", params={"year": year},
                                     timeout=REQUEST_TIMEOUT_SECONDS).json().get("eclipses_in_year", [])
            for item in eclipses:
                events.append(Event.from_usno_eclipse_api(item))
        except Exception as e:
            logger.error("Error getting solar eclipses from USNO API: " + str(e))
            raise e
        return events

    def _get_moon_phases(self, year):
        events = []
        try:
            phases = requests.get(f"{self.BASE_URL}/moon/phases/year", params={"year": year},
                                   timeout=REQUEST_TIMEOUT_SECONDS).json().get("phasedata", [])
            for item in phases:
                events.append(Event.from_usno_moon_phase_api(item))
        except Exception as e:
            logger.error("Error getting moon phases from USNO API: " + str(e))
            raise e
        return events


class LaunchLibraryAPI:
    """Rocket launches via the free Launch Library 2 API (thespacedevs.com).
    No account or API key required for this usage.

    Unlike Hebcal/USNO/NobelPrizeSchedule, this IS wired into
    CalendarAggregator.get_events() -- launch schedules slip, scrub, and get
    added constantly, so this is genuinely live data refreshed on
    update_event_cache's cycle, not the backfill job.

    Deliberately does NOT fetch "a whole year" the way Nager/Inadiutorium/
    Hijri do: the free, unauthenticated tier is capped at 15 requests/hour
    per IP (TheSpaceDevs' own documented limit), and two years of global
    launch activity could take dozens of paginated requests to page through.
    Instead this fetches a short rolling window with a large page size
    (well under the limit per call), which also better reflects that launch
    dates aren't meaningfully known much further out than that anyway.
    """
    BASE_URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/"
    WINDOW_DAYS = 120
    PAGE_LIMIT = 100

    def __init__(self):
        pass

    def get_events(self, year=-1):
        # year is accepted for interface consistency with every other
        # source (CalendarAggregator.get_events(year) calls all of them the
        # same way), but a short forward-looking window from *now* is
        # fetched regardless of which year is asked for -- see class
        # docstring. The caller (fetch_live_calendar_events) already filters
        # results down to whichever year's date range it actually wants, so
        # this is safe: launches outside that range are simply dropped
        # there, the same way this method's caller already handles every
        # other source.
        events = []
        try:
            results = requests.get(self.BASE_URL, params={"limit": self.PAGE_LIMIT},
                                    timeout=REQUEST_TIMEOUT_SECONDS).json().get("results", [])
            for item in results:
                events.append(Event.from_launch_library_api(item))
        except Exception as e:
            logger.error("Error getting events from Launch Library API: " + str(e))
            raise e
        return events


class NobelPrizeSchedule:
    """Nobel Prize announcement dates -- a manually curated schedule, not a
    live API call.

    No confirmed API exposes upcoming Nobel Prize announcement *dates*: the
    official api.nobelprize.org is a historical database of past prizes and
    laureates (keyed by year, not a specific date), and the actual schedule
    is published by the Nobel Foundation as a press release each year, a few
    months ahead, with no structured feed found for it.

    SCHEDULE below needs updating by hand once the Nobel Foundation
    announces each coming year's dates. For any year not listed, get_events()
    naively reuses the most recently curated earlier year's month/day for
    each category -- an approximation (actual dates shift by a few days
    year to year), not a verified prediction, but better than nothing once
    this list falls behind.
    """
    SCHEDULE = {
        2026: {
            'Physiology or Medicine': (10, 5),
            'Physics': (10, 6),
            'Chemistry': (10, 7),
            'Literature': (10, 8),
            'Peace': (10, 9),
            'Economic Sciences': (10, 12),
        },
    }

    def _categories_for_year(self, year):
        if year in self.SCHEDULE:
            return self.SCHEDULE[year]

        earlier_years = [y for y in self.SCHEDULE if y < year]
        if not earlier_years:
            return None
        return self.SCHEDULE[max(earlier_years)]

    def get_events(self, year=-1):
        categories = self._categories_for_year(year)
        if not categories:
            return []

        events = []
        for category, (month, day) in categories.items():
            events.append(Event(
                name=f"Nobel Prize in {category} Announcement",
                date=datetime.datetime(year, month, day),
                source="Nobel Prize",
                fixed=False,
            ))
        return events


class CalendarAggregator:
    def __init__(self):
        # self.holiday_api = HolidayAPI(config.holiday_api_key)
        self.public_holidays_api = NagerPublicHolidaysAPI()
        self.hijri_calendar_api = HijriCalendarAPI()
        # Genuinely live/changeable data -- merged into get_events() below,
        # same as the two above. Real-world Islamic month starts can involve
        # an actual moon-sighting decision a purely computed prediction
        # might not track exactly, so Hijri stays on this cycle rather than
        # joining Inadiutorium below, even though both are rule-computed.
        self.launch_library_api = LaunchLibraryAPI()
        # Computed/curated, not merged into get_events() below -- see
        # InadiutoriumAPI's/HebcalAPI's/NobelPrizeSchedule's docstrings.
        # Used instead by backfill_computed_calendar_events.
        self.inadiutorium_api = InadiutoriumAPI()
        self.hebcal_api = HebcalAPI()
        self.usno_astronomical_events_api = USNOAstronomicalEventsAPI()
        self.nobel_prize_schedule = NobelPrizeSchedule()

    def get_events(self, year):
        # holidays = self.holiday_api.get_events(["US", "DE", "GB", "CA", "RU"], year)
        public_holidays = self.public_holidays_api.get_events(["US", "DE", "GB", "CA", "RU"], year)
        hijri = self.hijri_calendar_api.get_events(year)
        launches = self.launch_library_api.get_events(year)

        all_events = []
        Event.merge_events(all_events, public_holidays)
        Event.merge_events(all_events, hijri)
        Event.merge_events(all_events, launches)
        all_events.sort(key=lambda e: (e.date))
        return all_events


