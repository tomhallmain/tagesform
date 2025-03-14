import pytest
from flask import url_for
from app.models import User

def test_login_page(client):
    """Test login page loads correctly"""
    response = client.get('/login', follow_redirects=True)
    assert response.status_code == 200
    assert b'Login' in response.data

def test_register_page(client):
    """Test register page loads correctly"""
    response = client.get('/register', follow_redirects=True)
    assert response.status_code == 200
    assert b'Register' in response.data

def test_successful_registration(client, db_session):
    """Test successful user registration"""
    response = client.post('/register', data={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'testpass123'
    }, follow_redirects=True)
    assert response.status_code == 200  # Should end up at login page
    assert b'Registration successful' in response.data
    
    # Verify user was created
    user = User.query.filter_by(username='testuser').first()
    assert user is not None
    assert user.email == 'test@example.com'
    assert user.check_password('testpass123')

def test_duplicate_username_registration(client, test_user):
    """Test registration with existing username"""
    response = client.post('/register', data={
        'username': test_user.username,
        'email': 'different@example.com',
        'password': 'testpass123'
    }, follow_redirects=True)
    assert b'Username already exists' in response.data

def test_duplicate_email_registration(client, test_user):
    """Test registration with existing email"""
    response = client.post('/register', data={
        'username': 'different_user',
        'email': test_user.email,
        'password': 'testpass123'
    }, follow_redirects=True)
    assert b'Email already registered' in response.data

def test_successful_login(client, test_user):
    """Test successful login"""
    response = client.post('/login', data={
        'username': test_user.username,
        'password': 'test123'  # Match password from conftest.py
    }, follow_redirects=True)
    assert response.status_code == 200  # After following redirects
    
    # Check session
    with client.session_transaction() as sess:
        assert '_user_id' in sess

def test_invalid_login(client, test_user):
    """Test login with invalid credentials"""
    # Make sure we start with a clean session and logout any current user
    with client.session_transaction() as sess:
        sess.clear()
    client.get('/logout', follow_redirects=True)  # Ensure we're logged out
    
    # First request - should get a redirect
    response = client.post('/login', data={
        'username': test_user.username,
        'password': 'wrongpassword'
    }, follow_redirects=False)
    
    # Check for redirect
    assert response.status_code == 302
    assert response.location == '/login'  # Should redirect back to login
    
    # Now follow the redirect
    response = client.get(response.location)
    assert response.status_code == 200
    
    # Check that we're not logged in
    with client.session_transaction() as sess:
        assert '_user_id' not in sess
    
    # Check for error message
    assert b'Invalid username or password' in response.data
    
    # Check that we're on the login page
    assert b'Sign in to your account' in response.data

def test_logout(client, auth):
    """Test logout functionality"""
    auth.login()
    
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    
    # Check session
    with client.session_transaction() as sess:
        assert '_user_id' not in sess

def test_login_required_redirect(client):
    """Test that protected routes redirect to login"""
    response = client.get('/profile/', follow_redirects=True)
    assert b'Login' in response.data
    assert response.request.path == '/login'

def test_profile_update(client, auth, test_user, db_session):
    """Test profile update functionality"""
    auth.login()
    
    # Update profile
    response = client.post('/profile/update', data={
        'username': 'updated_username',
        'email': 'updated@example.com',
        'new_password': 'newpass123',
        'confirm_password': 'newpass123'
    }, follow_redirects=True)
    
    assert b'Profile updated successfully' in response.data
    
    # Verify changes
    updated_user = User.query.get(test_user.id)
    assert updated_user.username == 'updated_username'
    assert updated_user.email == 'updated@example.com'
    assert updated_user.check_password('newpass123') 