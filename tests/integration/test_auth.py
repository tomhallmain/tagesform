import pytest
from flask import url_for
from urllib.parse import urlsplit
from app.models import User, db

from helpers import assert_in_response, expected_text

pytestmark = pytest.mark.integration

def test_login_page(client):
    """Test login page loads correctly"""
    response = client.get('/login', follow_redirects=True)
    assert response.status_code == 200
    assert_in_response(expected_text('Login - Tagesform'), response)

def test_register_page(client):
    """Test register page loads correctly"""
    response = client.get('/register', follow_redirects=True)
    assert response.status_code == 200
    # register.html is standalone -- doesn't extend base.html, so the nav's
    # _('Register') link never renders here; only the <title> does.
    assert_in_response(expected_text('Register - Tagesform'), response)

def test_successful_registration(client, db_session):
    """Test successful user registration"""
    response = client.post('/register', data={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'testpass123',
        'confirm_password': 'testpass123'
    }, follow_redirects=True)
    assert response.status_code == 200  # Should end up at login page
    assert_in_response(expected_text('Registration successful'), response)

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
        'password': 'testpass123',
        'confirm_password': 'testpass123'
    }, follow_redirects=True)
    assert_in_response(expected_text('Username already exists'), response)

def test_duplicate_email_registration(client, test_user):
    """Test registration with existing email"""
    response = client.post('/register', data={
        'username': 'different_user',
        'email': test_user.email,
        'password': 'testpass123',
        'confirm_password': 'testpass123'
    }, follow_redirects=True)
    assert_in_response(expected_text('Email already registered'), response)

def test_password_mismatch_registration(client):
    """Test registration with mismatched passwords"""
    response = client.post('/register', data={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'testpass123',
        'confirm_password': 'differentpass'
    }, follow_redirects=True)
    assert_in_response(expected_text('Passwords do not match'), response)

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

    # Check for redirect back to login. response.location's absolute-vs-relative
    # form varies by Werkzeug version, so compare on the path only.
    assert response.status_code == 302
    assert urlsplit(response.location).path == '/login'

    # Now follow the redirect
    response = client.get('/login')
    assert response.status_code == 200

    # Check that we're not logged in
    with client.session_transaction() as sess:
        assert '_user_id' not in sess

    # Check for error message
    assert_in_response(expected_text('Invalid username or password'), response)

    # Check that we're on the login page
    assert_in_response(expected_text('Sign in to your account'), response)

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
    assert_in_response(expected_text('Login - Tagesform'), response)
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

    assert_in_response(expected_text('Profile updated successfully'), response)

    # Verify changes
    updated_user = db.session.get(User, test_user.id)
    assert updated_user.username == 'updated_username'
    assert updated_user.email == 'updated@example.com'
    assert updated_user.check_password('newpass123')
