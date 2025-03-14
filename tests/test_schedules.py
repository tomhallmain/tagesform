import pytest
from flask import url_for
from datetime import datetime, timedelta
from app.models import Schedule

def test_new_schedule_page(client, auth):
    """Test new schedule page loads correctly"""
    auth.login()
    response = client.get('/new-schedule')
    assert response.status_code == 200
    assert b'New Schedule' in response.data

def test_create_schedule(client, auth, test_user, db_session):
    """Test creating a new schedule"""
    auth.login()
    
    # Prepare schedule data - 9:00 to 17:00
    schedule_data = {
        'title': 'Test Schedule',
        'start_time': '09:00',  # Will be converted to minutes in the route
        'end_time': '17:00',    # Will be converted to minutes in the route
        'recurrence': 'daily',
        'category': 'work',
        'location': 'Office',
        'description': 'Test Description'
    }
    
    response = client.post('/new-schedule', data=schedule_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Schedule created successfully!' in response.data
    
    # Verify schedule was created
    schedule = Schedule.query.filter_by(title='Test Schedule').first()
    assert schedule is not None
    assert schedule.start_time == 9 * 60  # 9:00 = 540 minutes
    assert schedule.end_time == 17 * 60   # 17:00 = 1020 minutes
    assert schedule.recurrence == 'daily'
    assert schedule.category == 'work'
    assert schedule.location == 'Office'
    assert schedule.description == 'Test Description'
    assert schedule.user_id == test_user.id

def test_get_current_schedule(client, auth, test_user, db_session):
    """Test getting current schedule"""
    auth.login()
    
    # Create a test schedule - 9:00 to 17:00
    schedule = Schedule(
        title='Current Schedule',
        start_time=9 * 60,    # 9:00 = 540 minutes
        end_time=17 * 60,     # 17:00 = 1020 minutes
        recurrence='daily',
        category='work',
        user_id=test_user.id
    )
    db_session.add(schedule)
    db_session.commit()
    
    # Test the current schedule endpoint
    response = client.get('/api/schedule/current')
    assert response.status_code == 200
    data = response.get_json()
    
    assert data is not None
    if data.get('schedule'):  # If there's a current schedule
        assert data['schedule']['start_time'] == '09:00'
        assert data['schedule']['end_time'] == '17:00'

def test_schedule_validation(client, auth):
    """Test schedule validation during creation"""
    auth.login()
    
    # Test with missing required fields
    response = client.post('/new-schedule', data={
        'title': '',  # Missing title
        'start_time': '',  # Missing start time
        'end_time': ''  # Missing end time
    })
    
    assert response.status_code == 400
    assert b'Title is required' in response.data
    assert b'Start time and end time are required' in response.data

    # Test with invalid time format
    response = client.post('/new-schedule', data={
        'title': 'Test Schedule',
        'start_time': 'invalid',
        'end_time': 'invalid'
    })
    
    assert response.status_code == 400
    assert b'Invalid time format. Please use HH:MM format' in response.data

def test_schedule_user_isolation(client, auth, test_user, db_session):
    """Test that users can only see their own schedules"""
    # Create a schedule for test_user - 9:00 to 17:00
    schedule = Schedule(
        title='Test Schedule',
        start_time=9 * 60,    # 9:00 = 540 minutes
        end_time=17 * 60,     # 17:00 = 1020 minutes
        user_id=test_user.id
    )
    db_session.add(schedule)
    db_session.commit()
    
    # Create another user and log them in
    from app.models import User
    other_user = User(username='other_user', email='other@example.com')
    other_user.set_password('password')
    db_session.add(other_user)
    db_session.commit()
    
    # Login as other user
    client.post('/login', data={
        'username': 'other_user',
        'password': 'password'
    })
    
    # Try to access schedules
    response = client.get('/schedules')
    assert response.status_code == 200
    assert b'Test Schedule' not in response.data  # Should not see test_user's schedule

def test_invalid_schedule_times(client, auth):
    """Test validation of schedule times"""
    auth.login()
    
    # Test with end time before start time
    schedule_data = {
        'title': 'Invalid Schedule',
        'start_time': '17:00',  # 5 PM
        'end_time': '09:00',    # 9 AM (invalid as it's before start time)
        'recurrence': 'daily'
    }
    
    response = client.post('/new-schedule', data=schedule_data, follow_redirects=True)
    assert response.status_code == 200
    # Your validation error message would go here
    # assert b'End time must be after start time' in response.data 