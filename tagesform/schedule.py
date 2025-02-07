
from utils.translations import I18N

_ = I18N._

class Schedule:
    def __init__(self, name=None, enabled=True, weekday_options=[], start_time=None, end_time=None, shutdown_time=None):
        self.name = _('New Schedule') if name is None else name
        self.enabled = enabled
        self.weekday_options = weekday_options
        self.start_time = start_time
        self.end_time = end_time
        self.shutdown_time = shutdown_time

    def is_valid(self):
        return len(self.weekday_options) > 0

    def set_start_time(self, hour=0, minute=0):
        self.start_time = Schedule.get_time(hour=hour, minute=minute)

    def set_end_time(self, hour=0, minute=0):
        self.end_time = Schedule.get_time(hour=hour, minute=minute)

    def set_shutdown_time(self, hour=0, minute=0):
        self.shutdown_time = Schedule.get_time(hour=hour, minute=minute)

    def short_text(self):
        return str(self.name)

    def next_end(self, current_date):
        day_index = current_date.weekday()
        if self.end_time is None and self.shutdown_time is None:
            if len(self.weekday_options) == 7:
                return "unknown time"
            else:
                for i in range(len(self.weekday_options)):
                    next_i = (i + day_index + 1) % 7
                    if next_i not in self.weekday_options:
                        if i == 0:
                            return _("Tomorrow")
                        else:
                            return I18N.day_of_the_week(next_i)
                raise Exception("No more available times")
        elif self.end_time is not None:
            return self.readable_time(self.end_time)
        elif self.shutdown_time is not None:
            return self.readable_time(self.shutdown_time)
        else:
            raise Exception("No more available times")
    
    def calculate_generality(self):
        minutes_in_day = 24 * 60
        if (self.start_time is None or self.start_time == 0) and (self.end_time is None or self.end_time == 0):
            return float(len(self.weekday_options))
        elif self.start_time is None or self.start_time == 0:
            return float(self.end_time) / minutes_in_day
        elif self.end_time is None or self.end_time == 0:
            return (minutes_in_day - float(self.start_time)) / minutes_in_day
        else:
            return (float(self.end_time) - float(self.start_time)) / minutes_in_day

    @staticmethod
    def get_time(hour=0, minute=0):
        return hour * 60 + minute

    @staticmethod
    def from_dict(_dict):
        return Schedule(**_dict)

    def to_dict(self):
        return self.__dict__

    def __str__(self):
        if len(self.weekday_options) == 7:
            weekday_options = _("Every day")
        else:
            weekday_options = ", ".join(map(lambda i: I18N.day_of_the_week(i), self.weekday_options))
        return _("{0} - Days: {1} - Times: {2}-{3} - Shutdown: {4}").format(
            self.name, weekday_options, 
            self.readable_time(self.start_time),
            self.readable_time(self.end_time),
            self.readable_time(self.shutdown_time))

    def readable_time(self, time):
        if not time or time < 0:
            return "N/A"
        else:
            return "{0}:{1}".format(int(time / 60), time % 60)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Schedule) and self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

