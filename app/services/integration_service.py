from datetime import datetime, timedelta
from flask_login import current_user
from .calendar_aggregator import CalendarAggregator, format_event
from .open_weather import OpenWeatherAPI
from .schedules_manager import SchedulesManager
from ..utils.ancient_egyptian_calendar import to_ancient_egyptian_date, format_ancient_egyptian_date
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

    def get_calendar_events(self, start_date=None, end_date=None, user=None):
        """Get calendar events for the specified date range from the cache.

        Reads from EventCache rather than the live holiday/religious-calendar
        APIs -- those (Nager, Inadiutorium, Hijri) are refreshed periodically
        by the update_event_cache background job instead. Calling them
        synchronously here used to mean every dashboard load and every
        time-horizon tab click triggered minutes of live API calls (Inadiutorium
        alone issues one request per month, each taking upwards of 20 seconds).

        Includes: global rows (public holidays etc., user_id AND entity_id
        both NULL); `user`'s own custom-calendar rows; and entries from
        entities `user` owns or that are shared with them (NOT merely public
        ones -- see docs/entity-calendar.md's Ownership section for why).
        Never another user's custom-calendar rows, and never another user's
        private view of an entity they don't have access to.

        `user` defaults to the logged-in current_user, for the normal
        request path (the dashboard's /api/calendar/events). The
        suggestion-queue background job passes an explicit user instead,
        since it refreshes every user's queue outside of any request
        context, where current_user can't resolve.

        Each returned dict also carries an 'ancient_egyptian_date' field --
        the Ancient Egyptian civil-calendar equivalent of that event's date,
        computed for whatever date the event actually falls on (not just
        "today"), so it's visible across the day/week/month/year views this
        method already serves rather than being a separate "today only"
        display (see docs/egyptian-calendars.md's Part 2 Goals).
        """
        from ..models import Entity, EventCache, db

        if user is None:
            user = current_user

        try:
            if not start_date:
                start_date = datetime.now()

            visible_entity_ids = Entity.query.filter(
                db.or_(
                    Entity.user_id == user.id,
                    Entity.shared_with.contains([user.id])
                )
            ).with_entities(Entity.id)

            query = EventCache.query.filter(
                EventCache.date >= start_date,
                db.or_(
                    db.and_(EventCache.user_id.is_(None), EventCache.entity_id.is_(None)),
                    EventCache.user_id == user.id,
                    EventCache.entity_id.in_(visible_entity_ids)
                )
            )
            if end_date:
                query = query.filter(EventCache.date <= end_date)

            events = []
            for event in query.order_by(EventCache.date).all():
                event_dict = event.to_dict()
                event_dict['ancient_egyptian_date'] = format_ancient_egyptian_date(
                    to_ancient_egyptian_date(event.date)
                )
                events.append(event_dict)
            return events
        except Exception as e:
            return []  # Return empty list on error instead of raising

    def fetch_live_calendar_events(self, start_date=None, end_date=None):
        """Fetch calendar events directly from the live upstream APIs (Nager,
        Inadiutorium, Hijri) via CalendarAggregator, bypassing the cache.

        Used only by the update_event_cache background job to refresh
        EventCache -- request handlers should use get_calendar_events instead,
        which reads the cache that this method's caller populates.
        """
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
                    formatted_events.append(format_event(event))
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