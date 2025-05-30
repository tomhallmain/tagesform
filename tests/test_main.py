import pytest
from flask import url_for
from datetime import datetime, timedelta
from app.models import Activity, ScheduleRecord, Entity

def test_index_redirect_anonymous(client):
    """Test that anonymous users are redirected to login"""
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.location

def test_index_authenticated(client, auth):
    """Test that authenticated users see the dashboard"""
    auth.login()
    response = client.get('/')
    assert response.status_code == 200
    # Check for sections that are actually on the page
    assert b'Current Weather' in response.data
    assert b'Active Schedule' in response.data
    assert b'Coming Up' in response.data

def test_stats_endpoint(client, auth, test_user, db_session):
    """Test the stats API endpoint"""
    auth.login()
    
    # Create some test data
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    
    # Activity within a week
    activity1 = Activity(
        title='Test Activity 1',
        scheduled_time=now + timedelta(days=2),
        user_id=test_user.id
    )
    
    # Activity beyond a week
    activity2 = Activity(
        title='Test Activity 2',
        scheduled_time=now + timedelta(weeks=2),
        user_id=test_user.id
    )
    
    # Schedule - using full datetime objects
    schedule = ScheduleRecord(
        title='Test Schedule',
        start_time=tomorrow.replace(hour=9, minute=0, second=0, microsecond=0),  # 9 AM tomorrow
        end_time=tomorrow.replace(hour=17, minute=0, second=0, microsecond=0),   # 5 PM tomorrow
        user_id=test_user.id,
        recurrence='daily',  # Required field for ScheduleRecord
        enabled=True  # Required field for ScheduleRecord
    )
    
    # Place
    place = Entity(
        name='Test Place',
        category='restaurant',
        user_id=test_user.id
    )
    
    db_session.add_all([activity1, activity2, schedule, place])
    db_session.commit()
    
    # Test the stats endpoint
    response = client.get('/api/stats')
    assert response.status_code == 200
    data = response.get_json()
    
    assert data['weekly_count'] == 1  # Only activity1 is within a week
    assert data['schedule_count'] == 1
    assert data['places_count'] == 1

def test_health_check(client):
    """Test the health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    
    assert 'status' in data
    assert 'ollama_status' in data
    assert 'database' in data
    assert 'model' in data
    assert data['status'] == 'healthy' 