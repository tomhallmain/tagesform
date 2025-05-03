from .mixins import db
from datetime import date
from ..utils.translations import I18N

_ = I18N._

class ScheduleRecord(db.Model):
    __tablename__ = 'schedule'  # Keep the original table name
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_time = db.Column(db.Integer, nullable=False)  # Minutes since midnight (0-1440)
    end_time = db.Column(db.Integer, nullable=False)    # Minutes since midnight (0-1440)
    recurrence = db.Column(db.String(50))  # daily, weekly, monthly, etc.
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50))
    location = db.Column(db.String(200))
    description = db.Column(db.Text)
    annual_dates = db.Column(db.JSON)  # List of {month: int, day: int} objects for annual recurring dates
    weekday_options = db.Column(db.JSON)  # List of weekday indices (0-6) for weekly schedules
    enabled = db.Column(db.Boolean, default=True)  # Add enabled field

    @staticmethod
    def time_to_minutes(time_str):
        """Convert HH:MM time string to minutes since midnight"""
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes

    @staticmethod
    def minutes_to_time(minutes):
        """Convert minutes since midnight to HH:MM time string"""
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"

    def to_dict(self):
        """Convert schedule to dictionary format"""
        return {
            'id': self.id,
            'title': self.title,
            'start_time': self.minutes_to_time(self.start_time),
            'end_time': self.minutes_to_time(self.end_time),
            'recurrence': self.recurrence,
            'category': self.category,
            'location': self.location,
            'description': self.description,
            'annual_dates': self.annual_dates or [],
            'weekday_options': self.weekday_options or [],
            'enabled': self.enabled
        }

    def is_valid(self):
        """Check if the schedule is valid"""
        if self.recurrence == 'weekly':
            return bool(self.weekday_options)  # Must have weekday options for weekly schedules
        elif self.recurrence == 'annual':
            return bool(self.annual_dates)  # Must have annual dates for annual schedules
        return self.recurrence in ['daily', 'weekdays', 'monthly']

    def set_start_time(self, hour=0, minute=0):
        """Set the start time in minutes since midnight"""
        self.start_time = self.get_time(hour=int(hour), minute=int(minute))

    def set_end_time(self, hour=0, minute=0):
        """Set the end time in minutes since midnight"""
        self.end_time = self.get_time(hour=int(hour), minute=int(minute))

    def short_text(self):
        """Return a short text representation of the schedule"""
        return str(self.title)

    def next_end(self, current_date):
        """Get the next end time for the schedule"""
        if self.recurrence == 'annual' and self.annual_dates:
            # For annual schedules, find the next annual date
            current_month = current_date.month
            current_day = current_date.day
            
            # Sort annual dates by month and day
            sorted_dates = sorted(self.annual_dates, key=lambda x: (x['month'], x['day']))
            
            # Find the next date
            for date in sorted_dates:
                if (date['month'] > current_month) or \
                   (date['month'] == current_month and date['day'] > current_day):
                    return f"{date['month']}/{date['day']}"
            
            # If no future dates this year, return the first date of next year
            if sorted_dates:
                first_date = sorted_dates[0]
                return f"{first_date['month']}/{first_date['day']} (next year)"
            return "No annual dates set"
            
        if self.end_time is None:
            raise Exception("Schedule must have an end time")
            
        return self.readable_time(self.end_time)
    
    def calculate_generality(self):
        """Calculate how general/specific this schedule is"""
        minutes_in_day = 24 * 60
        if (self.start_time is None or self.start_time == 0) and (self.end_time is None or self.end_time == 0):
            return 1.0 if self.recurrence == 'daily' else 0.5
        elif self.start_time is None or self.start_time == 0:
            return float(self.end_time) / minutes_in_day
        elif self.end_time is None or self.end_time == 0:
            return (minutes_in_day - float(self.start_time)) / minutes_in_day
        else:
            return (float(self.end_time) - float(self.start_time)) / minutes_in_day

    @staticmethod
    def get_time(hour=0, minute=0):
        """Convert hours and minutes to minutes since midnight"""
        try:
            return int(hour) * 60 + int(minute)
        except (ValueError, TypeError):
            return None

    def readable_time(self, time):
        """Convert minutes since midnight to readable time string"""
        if time is None or (isinstance(time, (int, float)) and time < 0):
            return "N/A"
        try:
            time_val = int(time)
            return "{0:02d}:{1:02d}".format(time_val // 60, time_val % 60)
        except (ValueError, TypeError):
            return "N/A"

    def __str__(self):
        """String representation of the schedule"""
        if self.recurrence == 'annual' and self.annual_dates:
            dates_str = ", ".join(f"{date['month']}/{date['day']}" for date in sorted(self.annual_dates, key=lambda x: (x['month'], x['day'])))
            return _("{0} - Annual Dates: {1} - Times: {2}-{3}").format(
                self.title, dates_str,
                self.readable_time(self.start_time),
                self.readable_time(self.end_time))
        elif self.recurrence == 'daily':
            weekday_options = _("Every day")
        else:
            weekday_options = self.recurrence.capitalize()
        return _("{0} - Days: {1} - Times: {2}-{3}").format(
            self.title, weekday_options, 
            self.readable_time(self.start_time),
            self.readable_time(self.end_time))

    def __eq__(self, other: object) -> bool:
        """Equality comparison"""
        return isinstance(other, ScheduleRecord) and self.title == other.title

    def __hash__(self) -> int:
        """Hash function"""
        return hash(self.title) 