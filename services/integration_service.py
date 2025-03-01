from datetime import datetime
from tagesform.calendar_aggregator import EventGroup
from tagesform.open_weather import OpenWeatherAPI
from tagesform.schedules_manager import SchedulesManager
from utils.config import config

class IntegrationService:
    def __init__(self):
        self.weather_api = OpenWeatherAPI()
        self.schedules_manager = SchedulesManager()
        self.event_group = EventGroup()
        
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
        """Get the currently active schedule."""
        try:
            current_time = datetime.now()
            schedule = self.schedules_manager.get_active_schedule(current_time)
            if isinstance(schedule, dict) and "error" in schedule:
                return schedule
            
            if schedule:
                schedule_dict = schedule.to_dict()
                # Convert time values to readable format
                schedule_dict['start_time'] = schedule.readable_time(schedule.start_time)
                schedule_dict['end_time'] = schedule.readable_time(schedule.end_time)
                schedule_dict['shutdown_time'] = schedule.readable_time(schedule.shutdown_time) if schedule.shutdown_time else None
                return schedule_dict
            return None
        except Exception as e:
            return {"error": str(e)}
    
    def get_calendar_events(self, start_date=None, end_date=None):
        """Get calendar events for the specified date range."""
        try:
            if not start_date:
                start_date = datetime.now()
            events = self.event_group.get_events(start_date, end_date)
            return events
        except Exception as e:
            return {"error": str(e)}
    
    def get_dashboard_data(self, city=None):
        """Get combined dashboard data including weather, schedule, and calendar events."""
        current_weather = self.get_current_weather(city)
        current_schedule = self.get_current_schedule()
        today_events = self.get_calendar_events()
        
        return {
            "weather": current_weather,
            "schedule": current_schedule,
            "events": today_events
        }

# Create a singleton instance
integration_service = IntegrationService() 