from datetime import datetime, timedelta
from flask_login import current_user
from .calendar_aggregator import CalendarAggregator
from .open_weather import OpenWeatherAPI
from .schedules_manager import SchedulesManager
from ..utils.config import config
from ..utils.logging_setup import get_logger

logger = get_logger('integration_service')

class IntegrationService:
    def __init__(self):
        self.weather_api = OpenWeatherAPI()
        self.schedules_manager = SchedulesManager()
        self.calendar_aggregator = CalendarAggregator()

    def get_current_weather(self, city=None):
        """Get current weather for the specified city or default city."""
        try:
            if not city:
                city = config.open_weather_city
            weather = self.weather_api.get_weather_for_city(city)
            return weather.to_dict() if weather else {"error": "Could not fetch weather data"}
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            return {"error": str(e)}

    def get_current_schedule(self):
        """Get the currently active schedule"""
        try:
            current_time = datetime.now()
            logger.debug(f"Getting active schedule for user {current_user.id} at {current_time}")
            
            schedule = self.schedules_manager.get_active_schedule(current_time, current_user.id)
            logger.debug(f"Retrieved schedule: {schedule}")
            
            if isinstance(schedule, dict) and "error" in schedule:
                logger.error(f"Schedule error: {schedule['error']}")
                return schedule
            
            if schedule:
                schedule_dict = schedule.to_dict()
                # Convert time values to readable format
                schedule_dict['start_time'] = schedule.readable_time(schedule.start_time)
                schedule_dict['end_time'] = schedule.readable_time(schedule.end_time)
                logger.debug(f"Formatted schedule dict: {schedule_dict}")
                return schedule_dict
                
            logger.warning(f"No active schedule found for user {current_user.id}")
            return None
        except Exception as e:
            logger.error(f"Error getting current schedule: {str(e)}", exc_info=True)
            raise Exception(f"Error getting current schedule: {str(e)}")

    def get_calendar_events(self, start_date=None, end_date=None):
        """Get calendar events for the specified date range."""
        try:
            if not start_date:
                start_date = datetime.now()
            # Get events for the current year
            events = self.calendar_aggregator.get_events(start_date.year)
            # Filter events by date range if end_date is specified
            if end_date:
                events = [e for e in events if start_date <= e.date <= end_date]
            else:
                # Otherwise just get events from start_date onwards
                events = [e for e in events if e.date >= start_date]
            
            if not isinstance(events, list):
                return []
                
            formatted_events = []
            for event in events:
                try:
                    formatted_event = {
                        'title': str(event.name) if event.name else 'Untitled Event',
                        'start_time': event.date.strftime('%Y-%m-%d %H:%M') if event.date else None,
                        'description': str(event.notes[0]) if event.notes else None,
                        'location': str(event.countries[0]) if event.countries else None,
                        'sources': list(map(str, event.sources)) if event.sources else []
                    }
                    formatted_events.append(formatted_event)
                except Exception as e:
                    continue  # Skip events that can't be formatted
                    
            return formatted_events
        except Exception as e:
            return []  # Return empty list on error instead of raising

    def get_dashboard_data(self, city=None):
        """Get combined dashboard data including weather and schedule."""
        try:
            current_weather = self.get_current_weather(city)
            current_schedule = self.get_current_schedule()
            
            # Get activities and schedules for different timeframes
            now = datetime.utcnow()
            activities_data = {
                'day': self._get_activities_for_timeframe(now, now + timedelta(days=1)),
                'week': self._get_activities_for_timeframe(now, now + timedelta(weeks=1)),
                'next_week': self._get_activities_for_timeframe(now + timedelta(weeks=1), now + timedelta(weeks=2)),
                'month': self._get_activities_for_timeframe(now, now + timedelta(days=30)),
                'next_month': self._get_activities_for_timeframe(now + timedelta(days=30), now + timedelta(days=60)),
                'year': self._get_activities_for_timeframe(now, now + timedelta(days=365))
            }
            
            return {
                "weather": current_weather,
                "schedule": current_schedule,
                "activities": activities_data
            }
        except Exception as e:
            raise Exception(f"Error getting dashboard data: {str(e)}")

    def _get_activities_for_timeframe(self, start_time, end_time):
        """Helper method to get activities and schedules for a specific timeframe."""
        from ..models import Activity, ScheduleRecord
        from flask_login import current_user
        
        # Get activities
        activities = Activity.query.filter(
            Activity.user_id == current_user.id,
            Activity.status == 'upcoming',
            Activity.scheduled_time >= start_time,
            Activity.scheduled_time <= end_time
        ).order_by(Activity.scheduled_time, Activity.importance.desc()).all()
        
        # Get schedules
        schedules = ScheduleRecord.query.filter_by(user_id=current_user.id, enabled=True).all()
        
        # Convert activities to dict and add is_schedule field
        result = []
        for activity in activities:
            activity_dict = activity.to_dict()
            activity_dict['is_schedule'] = False
            result.append(activity_dict)
        
        # Add schedules that match the timeframe
        for schedule_record in schedules:
            # For annual schedules, check if any dates fall within the timeframe
            if schedule_record.recurrence == 'annual' and schedule_record.annual_dates:
                for date in schedule_record.annual_dates:
                    # Create a datetime for this year's occurrence
                    schedule_date = datetime(start_time.year, date['month'], date['day'])
                    # If the date has already passed this year, check next year
                    if schedule_date < start_time:
                        schedule_date = datetime(start_time.year + 1, date['month'], date['day'])
                    if start_time <= schedule_date <= end_time:
                        result.append({
                            'id': f"schedule_{schedule_record.id}",
                            'title': schedule_record.title,
                            'description': f"Annual schedule for {date['month']}/{date['day']}",
                            'scheduled_time': schedule_date.isoformat(),
                            'importance': 0.5,  # Default importance for schedules
                            'status': 'upcoming',
                            'category': 'schedule',
                            'duration': None,
                            'location': None,
                            'participants': None,
                            'notes': None,
                            'is_schedule': True,
                            'schedule_details': {
                                'start_time': schedule_record.readable_time(schedule_record.start_time),
                                'end_time': schedule_record.readable_time(schedule_record.end_time)
                            }
                        })
            # For regular schedules, check if any weekdays fall within the timeframe
            else:
                current_date = start_time
                while current_date <= end_time:
                    if schedule_record.recurrence == 'daily' or \
                       (schedule_record.recurrence == 'weekdays' and current_date.weekday() < 5) or \
                       (schedule_record.recurrence == 'weekly' and schedule_record.weekday_options and current_date.weekday() in schedule_record.weekday_options):
                        result.append({
                            'id': f"schedule_{schedule_record.id}_{current_date.strftime('%Y%m%d')}",
                            'title': schedule_record.title,
                            'description': f"Regular schedule for {current_date.strftime('%A')}",
                            'scheduled_time': current_date.isoformat(),
                            'importance': 0.5,  # Default importance for schedules
                            'status': 'upcoming',
                            'category': 'schedule',
                            'duration': None,
                            'location': None,
                            'participants': None,
                            'notes': None,
                            'is_schedule': True,
                            'schedule_details': {
                                'start_time': schedule_record.readable_time(schedule_record.start_time),
                                'end_time': schedule_record.readable_time(schedule_record.end_time)
                            }
                        })
                    current_date += timedelta(days=1)
        
        # Sort all items by scheduled_time
        result.sort(key=lambda x: x['scheduled_time'])
        return result

# Create a singleton instance
integration_service = IntegrationService() 