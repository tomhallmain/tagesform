
import datetime

from tagesform.schedule import Schedule
from utils.app_info_cache import app_info_cache
from utils.utils import Utils

class ScheduledShutdownException(Exception):
    """Exception raised when a scheduled shutdown is requested."""
    pass


class SchedulesManager:
    default_schedule = Schedule(name="Default", enabled=True, weekday_options=[0,1,2,3,4,5,6])
    recent_schedules = []
    last_set_schedule = None
    MAX_PRESETS = 50
    schedule_history = []

    def __init__(self):
        pass

    @staticmethod
    def set_schedules():
        for schedule_dict in list(app_info_cache.get("recent_schedules", default_val=[])):
            SchedulesManager.recent_schedules.append(Schedule.from_dict(schedule_dict))

    @staticmethod
    def store_schedules():
        schedule_dicts = []
        for schedule in SchedulesManager.recent_schedules:
            schedule_dicts.append(schedule.to_dict())
        app_info_cache.set("recent_schedules", schedule_dicts)

    @staticmethod
    def get_schedule_by_name(name):
        for schedule in SchedulesManager.recent_schedules:
            if name == schedule.name:
                return schedule
        raise Exception(f"No schedule found with name: {name}. Set it on the Schedules Window.")

    @staticmethod
    def get_history_schedule(start_index=0):
        # Get a previous schedule.
        schedule = None
        for i in range(len(SchedulesManager.schedule_history)):
            if i < start_index:
                continue
            schedule = SchedulesManager.schedule_history[i]
            break
        return schedule

    @staticmethod
    def update_history(schedule):
        if len(SchedulesManager.schedule_history) > 0 and \
                schedule == SchedulesManager.schedule_history[0]:
            return
        SchedulesManager.schedule_history.insert(0, schedule)
        if len(SchedulesManager.schedule_history) > SchedulesManager.MAX_PRESETS:
            del SchedulesManager.schedule_history[-1]

    @staticmethod
    def next_schedule(alert_callback):
        if len(SchedulesManager.recent_schedules) == 0:
            alert_callback(_("Not enough schedules found."))
        next_schedule = SchedulesManager.recent_schedules[-1]
        SchedulesManager.recent_schedules.remove(next_schedule)
        SchedulesManager.recent_schedules.insert(0, next_schedule)
        return next_schedule

    @staticmethod
    def refresh_schedule(schedule):
        SchedulesManager.update_history(schedule)
        if schedule in SchedulesManager.recent_schedules:
            SchedulesManager.recent_schedules.remove(schedule)
        SchedulesManager.recent_schedules.insert(0, schedule)

    @staticmethod
    def delete_schedule(schedule):
        if schedule is not None and schedule in SchedulesManager.recent_schedules:
            SchedulesManager.recent_schedules.remove(schedule)

    @staticmethod
    def get_active_schedule(datetime):
        assert datetime is not None
        day_index = datetime.weekday()
        current_time = Schedule.get_time(datetime.hour, datetime.minute)
        partially_applicable = []
        no_specific_times = []
        for schedule in SchedulesManager.recent_schedules:
            skip = False
            if not schedule.enabled:
                skip = True
            # if schedule.shutdown_time is not None and schedule.voice == SchedulesManager.default_schedule.voice:
            #     Utils.log_debug(f"Skipping schedule {schedule} - a shutdown time is set on this schedule and it is assumed to be for shutdown purposes only.")
            #     skip = True
            if day_index not in schedule.weekday_options:
                Utils.log_debug(f"Skipping schedule {schedule} - today is index {day_index} - schedule weekday options {schedule.weekday_options}")
                skip = True
            if skip:
                continue
            if schedule.start_time is not None and schedule.start_time < current_time:
                if schedule.end_time is not None and schedule.end_time > current_time:
                    Utils.log(f"Schedule {schedule} is applicable")
                    return schedule
                else:
                    partially_applicable.append(schedule)
            elif schedule.end_time is not None and schedule.end_time > current_time:
                partially_applicable.append(schedule)
            elif (schedule.start_time is None and schedule.end_time is None) or \
                    (schedule.start_time == 0 and schedule.end_time == 0):
                no_specific_times.append(schedule)
        if len(partially_applicable) >= 1:
            partially_applicable.sort(key=lambda schedule: schedule.calculate_generality())
            schedules_text = "\n".join([str(schedule) for schedule in partially_applicable])
            Utils.log(f"Schedules are partially applicable:\n{schedules_text}")
            return partially_applicable[0]
        elif len(no_specific_times) >= 1:
            no_specific_times.sort(key=lambda schedule: schedule.calculate_generality())
            schedules_text = "\n".join([str(schedule) for schedule in no_specific_times])
            Utils.log(f"Schedules are applicable to today but have no specific times:\n{schedules_text}")
            return no_specific_times[0]
        else:
            return SchedulesManager.default_schedule

    @staticmethod
    def get_next_weekday_index_for_attr(attr, name, datetime):
        assert attr is not None and name is not None
        schedules = []
        for schedule in SchedulesManager.recent_schedules:
            if schedule.enabled and getattr(schedule, name) == attr:
                schedules.append(schedule)
        if len(schedules) == 0:
            return None
        schedules.sort(key=lambda schedule: schedule.start_time * (1+SchedulesManager.get_closest_weekday_index_to_datetime(schedule, datetime, total_days=True)))
        return SchedulesManager.get_closest_weekday_index_to_datetime(schedules[0], datetime)

    @staticmethod
    def get_closest_weekday_index_to_datetime(schedule, datetime, total_days=False):
        assert isinstance(schedule, Schedule) and datetime is not None
        datetime_index = datetime.weekday()
        for i in schedule.weekday_options:
            if i >= datetime_index:
                return i
        for i in schedule.weekday_options:
            return i + 7 if total_days else i
        raise Exception("Invalid schedule, no weekday options found")

    @staticmethod
    def check_for_shutdown_request(datetime):
        schedule_requesting_shutdown = SchedulesManager._check_for_shutdown_request(datetime)
        if schedule_requesting_shutdown is not None:
            raise ScheduledShutdownException(f"Shutdown scheduled: {schedule_requesting_shutdown}")

    @staticmethod
    def _check_for_shutdown_request(datetime):
        assert datetime is not None
        day_index = datetime.weekday()
        current_time = Schedule.get_time(datetime.hour, datetime.minute)
        for schedule in SchedulesManager.recent_schedules:
            if not schedule.enabled or schedule.shutdown_time is None or day_index not in schedule.weekday_options:
                continue
            if schedule.shutdown_time < current_time:
                return schedule
        return None

    @staticmethod
    def get_hour():
        return datetime.datetime.now().hour


schedules_manager = SchedulesManager()

