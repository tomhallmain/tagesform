from datetime import datetime
from flask_login import current_user
import logging
from .calendar_aggregator import CalendarAggregator
from .open_weather import OpenWeatherAPI
from .schedules_manager import SchedulesManager
from ..utils.config import config

logger = logging.getLogger(__name__)

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
            
            return {
                "weather": current_weather,
                "schedule": current_schedule
            }
        except Exception as e:
            raise Exception(f"Error getting dashboard data: {str(e)}")

# Create a singleton instance
integration_service = IntegrationService() 