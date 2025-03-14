import pytest
from flask import url_for
from datetime import datetime, timedelta
from app.models import Activity
from unittest.mock import patch

def test_add_activity_page(client, auth):
    """Test add activity page loads correctly"""
    auth.login()
    response = client.get('/add-activity')
    assert response.status_code == 200
    assert b'Add Activity' in response.data

@patch('app.routes.activities.infer_activity_importance')
def test_add_activity(mock_infer, client, auth, test_user, db_session):
    """Test adding a new activity"""
    # Set up mock return value
    mock_infer.return_value = 0.75
    
    auth.login()
    
    # Prepare activity data
    scheduled_datetime = datetime.now() + timedelta(days=1)
    activity_data = {
        'title': 'Test Activity',
        'description': 'Test Description',
        'scheduled_date': scheduled_datetime.strftime('%Y-%m-%d'),
        'scheduled_time': scheduled_datetime.strftime('%H:%M'),
        'category': 'meeting',
        'duration': 60,
        'location': 'Test Location',
        'participants': 'John,Jane',
        'notes': 'Test Notes'
    }
    
    response = client.post('/add-activity', data=activity_data, follow_redirects=True)
    assert response.status_code == 200
    assert b'Activity added successfully!' in response.data
    
    # Verify activity was created
    activity = Activity.query.filter_by(title='Test Activity').first()
    assert activity is not None
    assert activity.description == 'Test Description'
    assert activity.category == 'meeting'
    assert activity.duration == 60
    assert activity.location == 'Test Location'
    assert activity.participants == ['John', 'Jane']
    assert activity.notes == 'Test Notes'
    assert activity.user_id == test_user.id
    assert activity.importance == 0.75  # Check mocked importance value

@patch('app.routes.activities.infer_activity_importance')
def test_analyze_activity(mock_infer, client, auth):
    """Test activity analysis endpoint"""
    # Set up mock return value
    mock_infer.return_value = 0.8
    
    auth.login()
    
    # Prepare activity data for analysis
    activity_data = {
        'title': 'Important Meeting',
        'description': 'Meeting with CEO about company strategy',
        'scheduled_time': datetime.now().isoformat(),
        'category': 'meeting',
        'duration': 60,
        'location': 'Conference Room',
        'participants': ['CEO', 'Executive Team']
    }
    
    response = client.post('/api/activities/analyze', 
                          json=activity_data,
                          headers={'Content-Type': 'application/json'})
    
    assert response.status_code == 200
    data = response.get_json()
    assert 'importance' in data
    assert data['importance'] == 0.8  # Check mocked importance value

def test_add_activity_validation(client, auth):
    """Test activity validation during creation"""
    auth.login()
    
    # Test with missing required fields
    response = client.post('/add-activity', data={
        'title': '',  # Missing title
        'scheduled_date': '',  # Missing date
        'scheduled_time': ''  # Missing time
    }, follow_redirects=True)
    
    assert response.status_code == 400
    assert b'Title is required' in response.data
    
    # Test with title but missing date/time
    response = client.post('/add-activity', data={
        'title': 'Test Activity',
        'scheduled_date': '',  # Missing date
        'scheduled_time': ''  # Missing time
    }, follow_redirects=True)
    
    assert response.status_code == 400
    assert b'Date and time are required' in response.data
    
    # Test with invalid date format
    response = client.post('/add-activity', data={
        'title': 'Test Activity',
        'scheduled_date': 'invalid-date',
        'scheduled_time': '12:00'
    }, follow_redirects=True)
    
    assert response.status_code == 400
    assert b'Invalid date or time format' in response.data

def test_activity_user_isolation(client, auth, test_user, db_session):
    """Test that users can only see their own activities"""
    # Create an activity for test_user
    activity = Activity(
        title='Test Activity',
        scheduled_time=datetime.now(),
        user_id=test_user.id
    )
    db_session.add(activity)
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
    
    # Try to access activities via the API endpoint
    response = client.get('/api/activities')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 0  # other_user should see no activities
    
    # Verify the activity exists but is not visible
    activity = Activity.query.filter_by(title='Test Activity').first()
    assert activity is not None
    assert activity.user_id == test_user.id 