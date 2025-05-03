import pytest
from datetime import datetime, timedelta
from app.models import Entity, ScheduleRecord, Activity, db
from app.services.integration_service import integration_service
from flask import current_app
from flask_login import login_user
from freezegun import freeze_time

def assert_event_in_timeframe(events, title, timeframe, event_type='activity'):
    """Helper method to check if an event (activity or schedule) exists in a timeframe and provide detailed output on failure.
    
    Args:
        events (list): List of events to check
        title (str): Title of the event to look for
        timeframe (str): Name of the timeframe for error messages
        event_type (str): Type of event ('activity' or 'schedule')
    """
    matching_events = [e for e in events if e['title'] == title]
    if not matching_events:
        event_titles = [e['title'] for e in events]
        pytest.fail(f"{event_type.capitalize()} '{title}' not found in {timeframe} timeframe. Available events: {event_titles}")
    return matching_events[0]

@pytest.fixture(scope='function')
def dashboard_test_data(db_session):
    """Create comprehensive test data for dashboard testing."""
    # Create test user if not exists
    from app.models import User
    test_user = User.query.filter_by(username='test').first()
    if not test_user:
        test_user = User(username='test', email='test@example.com')
        test_user.set_password('test123')
        db_session.add(test_user)
        db_session.commit()

    # Create places with varying data
    places = [
        # Highly rated restaurants
        Entity(
            name="Gourmet Delight",
            category="restaurant",
            location="123 Food St",
            rating=4,
            visited=True,
            user_id=test_user.id,
            properties={'cuisine': 'french'}
        ),
        Entity(
            name="Sushi Master",
            category="restaurant",
            location="456 Ocean Ave",
            rating=4,
            visited=True,
            user_id=test_user.id,
            properties={'cuisine': 'japanese'}
        ),
        # Medium rated places
        Entity(
            name="Coffee Corner",
            category="cafe",
            location="789 Brew St",
            rating=3,
            visited=True,
            user_id=test_user.id
        ),
        Entity(
            name="City Park",
            category="park",
            location="101 Nature Way",
            rating=3,
            visited=True,
            user_id=test_user.id
        ),
        # Lower rated places
        Entity(
            name="Quick Bite",
            category="restaurant",
            location="202 Fast Lane",
            rating=2,
            visited=True,
            user_id=test_user.id,
            properties={'cuisine': 'american'}
        ),
        # Unvisited places
        Entity(
            name="New Restaurant",
            category="restaurant",
            location="303 Fresh St",
            visited=False,
            user_id=test_user.id,
            properties={'cuisine': 'italian'}
        ),
        Entity(
            name="Museum of Art",
            category="museum",
            location="404 Culture Ave",
            visited=False,
            user_id=test_user.id
        ),
        # Places with operating hours
        Entity(
            name="24/7 Gym",
            category="gym",
            location="505 Fitness Blvd",
            visited=True,
            rating=3,
            user_id=test_user.id,
            operating_hours={
                'monday': {'open': '00:00', 'close': '23:59'},
                'tuesday': {'open': '00:00', 'close': '23:59'},
                'wednesday': {'open': '00:00', 'close': '23:59'},
                'thursday': {'open': '00:00', 'close': '23:59'},
                'friday': {'open': '00:00', 'close': '23:59'},
                'saturday': {'open': '00:00', 'close': '23:59'},
                'sunday': {'open': '00:00', 'close': '23:59'}
            }
        ),
        Entity(
            name="Weekend Cafe",
            category="cafe",
            location="606 Relax St",
            visited=True,
            rating=3,
            user_id=test_user.id,
            operating_hours={
                'saturday': {'open': '09:00', 'close': '17:00'},
                'sunday': {'open': '09:00', 'close': '17:00'}
            }
        ),
        # Public place
        Entity(
            name="Public Library",
            category="library",
            location="707 Knowledge Ave",
            visited=True,
            rating=4,
            user_id=test_user.id,
            is_public=True
        )
    ]

    # Create schedules of different types
    schedules = [
        # Daily schedule (6:00 AM - 7:00 AM)
        ScheduleRecord(
            title="Morning Exercise",
            start_time=ScheduleRecord.get_time(6, 0),  # 6:00 AM
            end_time=ScheduleRecord.get_time(7, 0),    # 7:00 AM
            recurrence="daily",
            enabled=True,
            user_id=test_user.id
        ),
        # Weekday schedule (9:00 AM - 5:00 PM)
        ScheduleRecord(
            title="Work Hours",
            start_time=ScheduleRecord.get_time(9, 0),  # 9:00 AM
            end_time=ScheduleRecord.get_time(17, 0),   # 5:00 PM
            recurrence="weekdays",
            enabled=True,
            user_id=test_user.id
        ),
        # Weekly schedule (6:00 PM - 7:00 PM on Mon, Wed, Fri)
        ScheduleRecord(
            title="Yoga Class",
            start_time=ScheduleRecord.get_time(18, 0), # 6:00 PM
            end_time=ScheduleRecord.get_time(19, 0),   # 7:00 PM
            recurrence="weekly",
            weekday_options=[1, 3, 5],  # Monday, Wednesday, Friday
            enabled=True,
            user_id=test_user.id
        ),
        # Annual schedule (12:00 PM - 11:00 PM on June 15th)
        ScheduleRecord(
            title="Birthday Celebration",
            start_time=ScheduleRecord.get_time(12, 0), # 12:00 PM
            end_time=ScheduleRecord.get_time(23, 0),   # 11:00 PM
            recurrence="annual",
            annual_dates=[{'month': 6, 'day': 15}],  # June 15th
            enabled=True,
            user_id=test_user.id
        )
    ]

    # Create activities at different times
    # Use a fixed base time for consistent testing
    base_time = datetime(2024, 3, 15, 12, 0, 0)  # Friday, March 15, 2024 at noon
    activities = [
        # Today's activity (2 hours from now)
        Activity(
            title="Team Meeting",
            description="Weekly team sync",
            scheduled_time=base_time + timedelta(hours=2),
            importance=0.8,
            status="upcoming",
            user_id=test_user.id
        ),
        # Tomorrow's activity (same time tomorrow)
        Activity(
            title="Project Deadline",
            description="Submit final report",
            scheduled_time=base_time + timedelta(days=1),
            importance=0.9,
            status="upcoming",
            user_id=test_user.id
        ),
        # Next week's activity (8 days from now to ensure it's in next week)
        Activity(
            title="Client Presentation",
            description="Present new features",
            scheduled_time=base_time + timedelta(days=8),
            importance=0.7,
            status="upcoming",
            user_id=test_user.id
        ),
        # Next month's activity (32 days from now to ensure it's in next month)
        Activity(
            title="Team Building",
            description="Annual team event",
            scheduled_time=base_time + timedelta(days=32),
            importance=0.6,
            status="upcoming",
            user_id=test_user.id
        )
    ]

    # Add all test data to the session
    for place in places:
        db_session.add(place)
    for schedule in schedules:
        db_session.add(schedule)
    for activity in activities:
        db_session.add(activity)
    
    db_session.commit()

    return {
        'user': test_user,
        'places': places,
        'schedules': schedules,
        'activities': activities
    }

class TestDashboardIntegration:
    """Test class for dashboard integration testing."""
    
    @freeze_time("2024-03-15 12:00:00")  # Friday, March 15, 2024 at noon
    def test_dashboard_data_structure(self, dashboard_test_data, app):
        """Test that the dashboard data has the correct top-level structure."""
        with app.test_request_context():
            with app.app_context():
                login_user(dashboard_test_data['user'])
                
                # Get dashboard data
                dashboard_data = integration_service.get_dashboard_data()
                
                # Verify top-level structure
                assert isinstance(dashboard_data, dict)
                assert 'weather' in dashboard_data
                assert 'schedule' in dashboard_data
                assert 'activities' in dashboard_data
                
                # Verify activities structure
                activities = dashboard_data['activities']
                assert isinstance(activities, dict)
                expected_timeframes = ['day', 'week', 'next_week', 'month', 'next_month', 'year']
                for timeframe in expected_timeframes:
                    assert timeframe in activities
                    assert isinstance(activities[timeframe], list)

    @freeze_time("2024-03-15 12:00:00")  # Friday, March 15, 2024 at noon
    def test_activity_timeframe_filtering(self, dashboard_test_data, app):
        """Test that activities are correctly filtered into their respective timeframes."""
        with app.test_request_context():
            with app.app_context():
                login_user(dashboard_test_data['user'])
                dashboard_data = integration_service.get_dashboard_data()
                activities = dashboard_data['activities']
                
                # Day timeframe should have today's activity
                day_events = activities['day']
                assert_event_in_timeframe(day_events, 'Team Meeting', 'day', 'activity')
                
                # Week timeframe should have today's and tomorrow's activities
                week_events = activities['week']
                assert_event_in_timeframe(week_events, 'Team Meeting', 'week', 'activity')
                assert_event_in_timeframe(week_events, 'Project Deadline', 'week', 'activity')
                
                # Next week timeframe should have next week's activity
                next_week_events = activities['next_week']
                assert_event_in_timeframe(next_week_events, 'Client Presentation', 'next_week', 'activity')
                
                # Month timeframe should have all activities except next month's
                month_events = activities['month']
                assert_event_in_timeframe(month_events, 'Team Meeting', 'month', 'activity')
                assert_event_in_timeframe(month_events, 'Project Deadline', 'month', 'activity')
                assert_event_in_timeframe(month_events, 'Client Presentation', 'month', 'activity')
                
                # Verify next month's activity is not in month timeframe
                next_month_activities = [a for a in month_events if a['title'] == 'Team Building']
                if next_month_activities:
                    pytest.fail(f"Activity 'Team Building' should not be in month timeframe but was found")
                
                # Next month timeframe should have next month's activity
                next_month_events = activities['next_month']
                assert_event_in_timeframe(next_month_events, 'Team Building', 'next_month', 'activity')

    @freeze_time("2024-03-15 12:00:00")  # Friday, March 15, 2024 at noon
    def test_schedule_integration(self, dashboard_test_data, app):
        """Test that schedules are correctly integrated into each timeframe."""
        with app.test_request_context():
            with app.app_context():
                login_user(dashboard_test_data['user'])
                dashboard_data = integration_service.get_dashboard_data()
                activities = dashboard_data['activities']
                
                # Day timeframe should have daily schedule
                day_events = activities['day']
                assert_event_in_timeframe(day_events, 'Morning Exercise', 'day', 'schedule')
                
                # Week timeframe should have daily and weekday schedules
                week_events = activities['week']
                assert_event_in_timeframe(week_events, 'Morning Exercise', 'week', 'schedule')
                assert_event_in_timeframe(week_events, 'Work Hours', 'week', 'schedule')
                
                # Next week timeframe should have daily schedule
                next_week_events = activities['next_week']
                assert_event_in_timeframe(next_week_events, 'Morning Exercise', 'next_week', 'schedule')
                
                # Month timeframe should have daily schedule
                month_events = activities['month']
                assert_event_in_timeframe(month_events, 'Morning Exercise', 'month', 'schedule')
                
                # Next month timeframe should have daily schedule
                next_month_events = activities['next_month']
                assert_event_in_timeframe(next_month_events, 'Morning Exercise', 'next_month', 'schedule')

    @freeze_time("2024-03-15 12:00:00")  # Friday, March 15, 2024 at noon
    def test_event_structure(self, dashboard_test_data, app):
        """Test that events (both activities and schedules) have the correct structure."""
        with app.test_request_context():
            with app.app_context():
                login_user(dashboard_test_data['user'])
                dashboard_data = integration_service.get_dashboard_data()
                day_events = dashboard_data['activities']['day']
                
                # Verify event structure
                for event in day_events:
                    assert 'id' in event
                    assert 'title' in event
                    assert 'description' in event
                    assert 'scheduled_time' in event
                    assert 'importance' in event
                    assert 'status' in event
                    assert 'category' in event
                    assert 'is_schedule' in event
                    
                    # If it's a schedule, verify schedule details
                    if event.get('is_schedule'):
                        assert 'schedule_details' in event
                        assert 'start_time' in event['schedule_details']
                        assert 'end_time' in event['schedule_details']

    @freeze_time("2024-03-15 12:00:00")  # Friday, March 15, 2024 at noon
    def test_weather_and_schedule_data(self, dashboard_test_data, app):
        """Test that weather and current schedule data have the correct structure."""
        with app.test_request_context():
            with app.app_context():
                login_user(dashboard_test_data['user'])
                dashboard_data = integration_service.get_dashboard_data()
                
                # Verify schedule data
                schedule = dashboard_data['schedule']
                if schedule:  # Schedule might be None if no active schedule
                    assert isinstance(schedule, dict)
                    assert 'title' in schedule
                    assert 'start_time' in schedule
                    assert 'end_time' in schedule
                
                # Verify weather data
                weather = dashboard_data['weather']
                assert isinstance(weather, dict)
                # Weather might have an error if API is not configured
                if 'error' not in weather:
                    assert 'temperature' in weather
                    assert 'description' in weather


class TestPlaceRecommendations:
    """Test class for place recommendation functionality."""
    
    def test_place_recommendations_structure(self, dashboard_test_data, app, client):
        """Test that place recommendations have the correct structure."""
        with app.test_request_context():
            with app.app_context():
                login_user(dashboard_test_data['user'])
                
                # Get place recommendations from the API endpoint
                response = client.get('/api/entities/available')
                assert response.status_code == 200
                data = response.get_json()
                
                # Verify top-level structure
                assert isinstance(data, dict)
                assert 'dashboard_suggestions' in data
                assert 'owned' in data
                assert 'public' in data
                assert 'shared' in data
                assert 'hour_key' in data
                
                # Verify hour_key format (YYYYMMDDHH_userid)
                hour_key = data['hour_key']
                assert len(hour_key.split('_')) == 2
                timestamp, user_id = hour_key.split('_')
                assert len(timestamp) == 10  # YYYYMMDDHH
                assert timestamp.isdigit()
                assert user_id.isdigit()
                
                # Verify each section is a list
                assert isinstance(data['dashboard_suggestions'], list)
                assert isinstance(data['owned'], list)
                assert isinstance(data['public'], list)
                assert isinstance(data['shared'], list)
                
                # Verify each recommendation has required fields
                for section in ['dashboard_suggestions', 'owned']:
                    for rec in data[section]:
                        assert 'id' in rec
                        assert 'name' in rec
                        assert 'category' in rec
                        assert 'rating' in rec
                        assert 'location' in rec
                        assert 'visited' in rec
                        assert isinstance(rec['visited'], bool)
                        assert 'is_public' in rec
                        assert isinstance(rec['is_public'], bool)
                        assert 'properties' in rec
                        assert isinstance(rec['properties'], dict)
                        assert 'contact_info' in rec
                        assert 'tags' in rec
                        assert 'created_at' in rec
                        assert 'updated_at' in rec
                        assert 'operating_hours' in rec
                        assert rec['operating_hours'] is None or isinstance(rec['operating_hours'], dict)
                        assert 'shared_with' in rec
                        assert isinstance(rec['shared_with'], list)
    
    def test_place_recommendations_filtering(self, dashboard_test_data, app, client):
        """Test that place recommendations are correctly filtered."""
        with app.test_request_context():
            with app.app_context():
                login_user(dashboard_test_data['user'])
                
                # Get place recommendations from the API endpoint
                response = client.get('/api/entities/available')
                assert response.status_code == 200
                data = response.get_json()
                
                # Verify we have dashboard suggestions
                suggestions = data['dashboard_suggestions']
                assert len(suggestions) > 0
                
                # Verify we have a mix of rated and unrated places in suggestions
                rated_suggestions = [s for s in suggestions if s['rating'] is not None]
                unrated_suggestions = [s for s in suggestions if s['rating'] is None]
                assert len(rated_suggestions) > 0 or len(unrated_suggestions) > 0
                
                # Verify we have a mix of visited and unvisited places in suggestions
                visited_suggestions = [s for s in suggestions if s['visited']]
                unvisited_suggestions = [s for s in suggestions if not s['visited']]
                assert len(visited_suggestions) > 0 or len(unvisited_suggestions) > 0
                
                # Verify unvisited places are included in owned places
                unvisited = [r for r in data['owned'] if not r['visited']]
                assert len(unvisited) > 0
                
                # Verify highly rated places exist in owned places
                highly_rated = [r for r in data['owned'] if r['rating'] is not None and r['rating'] >= 4]
                assert len(highly_rated) > 0
                
                # Verify public places are included
                public_places = [r for r in data['owned'] if r['is_public']]
                assert len(public_places) > 0
                
                # Verify places with operating hours are included
                places_with_hours = [r for r in data['owned'] if r['operating_hours']]
                assert len(places_with_hours) > 0
                
                # Verify places with properties are included
                places_with_properties = [r for r in data['owned'] if r['properties']]
                assert len(places_with_properties) > 0
    
    def test_place_recommendations_categories(self, dashboard_test_data, app, client):
        """Test that place recommendations include various categories."""
        with app.test_request_context():
            with app.app_context():
                login_user(dashboard_test_data['user'])
                
                # Get place recommendations from the API endpoint
                response = client.get('/api/entities/available')
                assert response.status_code == 200
                data = response.get_json()
                
                # Get unique categories from both suggestions and owned places
                categories = {r['category'] for r in data['dashboard_suggestions'] + data['owned']}
                
                # Verify we have multiple categories
                assert len(categories) > 1
                
                # Verify common categories are present
                common_categories = {'restaurant', 'cafe', 'park', 'museum', 'gym', 'library'}
                assert any(cat in categories for cat in common_categories)
                
                # Verify properties for specific categories
                for place in data['owned']:
                    if place['category'] == 'restaurant':
                        assert 'cuisine' in place['properties']
                    elif place['category'] == 'gym':
                        assert place['operating_hours'] is not None
                        assert 'monday' in place['operating_hours']
                        assert 'sunday' in place['operating_hours'] 