import pytest
from flask import url_for
from datetime import datetime, timedelta
from app.models import Activity, Schedule, Entity

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
    assert b'Dashboard' in response.data

def test_stats_endpoint(client, auth, test_user, db_session):
    """Test the stats API endpoint"""
    auth.login()
    
    # Create some test data
    now = datetime.utcnow()
    
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
    
    # Schedule
    schedule = Schedule(
        title='Test Schedule',
        start_time=now.time(),
        end_time=(now + timedelta(hours=1)).time(),
        user_id=test_user.id
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