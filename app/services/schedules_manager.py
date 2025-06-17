import datetime
from ..models import ScheduleRecord
from ..utils.app_info_cache import app_info_cache
from ..utils.utils import Utils
from ..utils.logging_setup import get_logger

logger = get_logger('schedules_manager')

class ScheduledShutdownException(Exception):
    """Exception raised when a scheduled shutdown is requested."""
    pass


class SchedulesManager:
    default_schedule = ScheduleRecord(
        title="Default",
        enabled=True,
        start_time=0,  # 00:00
        end_time=1440,  # 24:00
        recurrence="daily",
        user_id=1  # This will be updated when the schedule is used
    )
    last_set_schedule = None
    MAX_PRESETS = 50

    def __init__(self):
        pass

    @staticmethod
    def get_schedule_by_name(name, user_id):
        """Get a schedule by its title for a specific user"""
        schedule = ScheduleRecord.query.filter_by(title=name, user_id=user_id).first()
        if not schedule:
            logger.error(f"No schedule found with name: {name}")
            raise Exception(f"No schedule found with name: {name}. Set it on the Schedules Window.")
        return schedule

    @staticmethod
    def get_active_schedule(datetime, user_id):
        assert datetime is not None
        logger.debug(f"Finding active schedule for user {user_id} at {datetime}")
        
        day_index = datetime.weekday()
        current_time = ScheduleRecord.get_time(datetime.hour, datetime.minute)
        current_month = datetime.month
        current_day = datetime.day
        partially_applicable = []
        no_specific_times = []
        
        # Get all enabled schedules for the user
        schedules = ScheduleRecord.query.filter_by(user_id=user_id, enabled=True).all()
        logger.debug(f"Found {len(schedules)} enabled schedules for user {user_id}")
        
        for schedule in schedules:
            logger.debug(f"Checking schedule: {schedule.title} (recurrence: {schedule.recurrence})")
            skip = False
            if not schedule.enabled:
                skip = True
                
            # Check if this is an annual schedule
            if schedule.recurrence == 'annual' and schedule.annual_dates:
                # Check if today matches any of the annual dates
                is_annual_match = any(
                    date['month'] == current_month and date['day'] == current_day 
                    for date in schedule.annual_dates
                )
                if not is_annual_match:
                    logger.debug(f"Skipping annual schedule - no match for date {current_month}/{current_day}")
                    skip = True
            # Check for weekly schedules with custom weekday configuration
            elif schedule.recurrence == 'weekly' and hasattr(schedule, 'weekday_options'):
                if not schedule.weekday_options:
                    logger.warning(f"Skipping schedule {schedule} - no weekday options defined")
                    skip = True
                elif day_index not in schedule.weekday_options:
                    logger.debug(f"Skipping schedule {schedule} - today is index {day_index} - schedule weekday options {schedule.weekday_options}")
                    skip = True
            # Check other predefined recurrence types
            elif schedule.recurrence == 'weekdays' and day_index >= 5:  # Weekend
                logger.debug(f"Skipping schedule {schedule} - today is weekend")
                skip = True
            elif schedule.recurrence == 'daily':
                logger.debug("Daily schedule found")
                pass  # Always applicable
                
            if skip:
                continue
                
            if schedule.start_time is not None and schedule.start_time < current_time:
                if schedule.end_time is not None and schedule.end_time > current_time:
                    logger.info(f"Schedule {schedule} is applicable")
                    return schedule
                else:
                    logger.debug(f"Schedule {schedule} is partially applicable (start time)")
                    partially_applicable.append(schedule)
            elif schedule.end_time is not None and schedule.end_time > current_time:
                logger.debug(f"Schedule {schedule} is partially applicable (end time)")
                partially_applicable.append(schedule)
            elif (schedule.start_time is None and schedule.end_time is None) or \
                    (schedule.start_time == 0 and schedule.end_time == 0):
                logger.debug(f"Schedule {schedule} has no specific times")
                no_specific_times.append(schedule)
                
        if len(partially_applicable) >= 1:
            partially_applicable.sort(key=lambda schedule: schedule.calculate_generality())
            schedules_text = "\n".join([str(schedule) for schedule in partially_applicable])
            logger.info(f"Schedules are partially applicable:\n{schedules_text}")
            return partially_applicable[0]
        elif len(no_specific_times) >= 1:
            no_specific_times.sort(key=lambda schedule: schedule.calculate_generality())
            schedules_text = "\n".join([str(schedule) for schedule in no_specific_times])
            logger.info(f"Schedules are applicable to today but have no specific times:\n{schedules_text}")
            return no_specific_times[0]
        else:
            logger.warning(f"No applicable schedule found for user {user_id}, using default schedule")
            return SchedulesManager.default_schedule

    @staticmethod
    def get_next_weekday_index_for_attr(attr, name, datetime, user_id):
        assert attr is not None and name is not None
        schedules = []
        for schedule in ScheduleRecord.query.filter_by(user_id=user_id, enabled=True).all():
            if getattr(schedule, name) == attr:
                schedules.append(schedule)
        if len(schedules) == 0:
            return None
        schedules.sort(key=lambda schedule: schedule.start_time * (1+SchedulesManager.get_closest_weekday_index_to_datetime(schedule, datetime, total_days=True)))
        return SchedulesManager.get_closest_weekday_index_to_datetime(schedules[0], datetime)

    @staticmethod
    def get_closest_weekday_index_to_datetime(schedule, datetime, total_days=False):
        assert isinstance(schedule, ScheduleRecord) and datetime is not None
        datetime_index = datetime.weekday()
        
        # Handle different recurrence types
        if schedule.recurrence == 'daily':
            return datetime_index
        elif schedule.recurrence == 'weekdays':
            if datetime_index < 5:  # Weekday
                return datetime_index
            else:  # Weekend
                return 7 if total_days else 0   # Next Monday
        elif schedule.recurrence == 'weekly' and hasattr(schedule, 'weekday_options'):
            if not schedule.weekday_options:
                raise Exception(f"Schedule {schedule} has no weekday options")
            # For weekly schedules with custom weekday configuration, find the next applicable weekday
            for i in schedule.weekday_options:
                if i >= datetime_index:
                    return i
            return schedule.weekday_options[0] + 7 if total_days else schedule.weekday_options[0]
        elif schedule.recurrence == 'annual':
            if not schedule.annual_dates:
                raise Exception(f"Schedule {schedule} has no annual dates defined")
                
            current_month = datetime.month
            current_day = datetime.day
            
            # Sort annual dates by month and day
            sorted_dates = sorted(schedule.annual_dates, key=lambda x: (x['month'], x['day']))
            
            # Find the next date
            for date in sorted_dates:
                if (date['month'] > current_month) or \
                   (date['month'] == current_month and date['day'] > current_day):
                    # Create a datetime for this date in the current year
                    next_date = datetime.replace(month=date['month'], day=date['day'])
                    if total_days:
                        return (next_date - datetime).days
                    return next_date.weekday()
            
            # If no future dates this year, use the first date of next year
            if sorted_dates:
                first_date = sorted_dates[0]
                # Create a datetime for the first date in the next year
                next_date = datetime.replace(year=datetime.year + 1, month=first_date['month'], day=first_date['day'])
                if total_days:
                    return (next_date - datetime).days
                return next_date.weekday()
                
            raise Exception(f"Schedule {schedule} has no valid annual dates")
        else:
            raise Exception(f"Invalid recurrence type: {schedule.recurrence}")

    @staticmethod
    def get_hour():
        return datetime.datetime.now().hour


schedules_manager = SchedulesManager()

