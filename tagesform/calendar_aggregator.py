import datetime
import requests
import time

from utils.config import config
from utils.utils import Utils


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
        self.name = name
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
                self.countries.extend(country)
            else:
                self.countries.append(country)
        if notes is not None:
            if isinstance(notes, list):
                self.notes.extend(notes)
            else:
                self.notes.append(notes)
        if other_name is not None:
            if not other_name in self.other_names:
                self.other_names.append(other_name)

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
        event_name = event["holidays"][0]
        new_event = Event(name=event_name,
            date=datetime.datetime.strptime(event["gregorian"]["date"], "%Y-%m-%d"),
            source="Hijri API",
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


class HolidayAPI:
    BASE_URL = "https://holidayapi.com/v1/holidays"

    def __init__(self, api_key=None):
        self.api_key = api_key

    def __build_url(self, country, year):
        return f"{self.BASE_URL}?key={self.api_key}&country={country}&year={year}"

    def get_events_for_country(self, country="US", year=-1):
        events = []
        try:
            events_json = requests.get(self.__build_url(country, year)).json()
            for event in events_json:
                events.append(Event.from_holiday_api(event))
        except Exception as e:
            Utils.log_red("Error getting events from Holiday API: " + str(e))
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
            events_json = requests.get(self.__build_url(country_code, year)).json()
            for event in events_json:
                events.append(Event.from_nager_public_holidays_api(event))
        except Exception as e:
            Utils.log_red("Error getting events from Nager Public Holidays API: " + str(e))
            raise e
        return events

    def get_events(self, country_codes=["US"], year=-1):
        events = []
        for country in country_codes:
            Event.merge_events(events, self.get_events_for_country(country, year))
        return events


class InadiutoriumAPI:
    BASE_URL = "http://calapi.inadiutorium.cz/api/v0/en/calendars/default/"

    def __init__(self):
        pass

    def __build_url(self, year=-1, month=-1):
        return self.BASE_URL + str(year) + "/" + str(month)

    def get_events_for_month(self, year=-1, month=-1):
        events = []
        try:
            events_json = requests.get(self.__build_url(year, month)).json()
            for event in events_json:
                events.append(Event.from_inadiutorium_api(event))
            time.sleep(0.5)
        except Exception as e:
            Utils.log_red("Error getting events from Inadiutorium API: " + str(e))
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
            dates_json  = requests.get(self.__build_url(month, year)).json()["data"]
            for date in dates_json:
                if len(date["hijri"]["holidays"]) > 0:
                    events.append(Event.from_hijri_api(date))
        except Exception as e:
            Utils.log_red("Error getting events from Hijri Calendar API: " + str(e))
            raise e
        return events

    def get_events(self, year=-1):
        events = []
        for month in range(0, 12):
            events.extend(self.get_events_for_month(year, month + 1))
        return events


class CalendarAggregator:
    def __init__(self):
        # self.holiday_api = HolidayAPI(config.holiday_api_key)
        self.public_holidays_api = NagerPublicHolidaysAPI()
        self.inadiutorium_api = InadiutoriumAPI()
        self.hijri_calendar_api = HijriCalendarAPI()

    def get_events(self, year):
        # holidays = self.holiday_api.get_events(["US", "DE", "GB", "CA", "RU"], year)
        inadiutorium = self.inadiutorium_api.get_events(year)
        public_holidays = self.public_holidays_api.get_events(["US", "DE", "GB", "CA", "RU"], year)
        hijri = self.hijri_calendar_api.get_events(year)

        all_events = []
        Event.merge_events(all_events, public_holidays)
        Event.merge_events(all_events, inadiutorium)
        Event.merge_events(all_events, hijri)
        all_events.sort(key=lambda e: (e.date))
        return all_events


