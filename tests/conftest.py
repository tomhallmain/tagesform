import os
import sys
import pytest
from flask import Flask, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, login_user
from sqlalchemy.orm import scoped_session, sessionmaker

# Add the project root directory to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Now we can import from app
from app import create_app
from app.models import User, db

@pytest.fixture(scope='session')
def app():
    """Create and configure a new app instance for each test session."""
    app = create_app('testing')
    
    # Configure test app for URL generation
    app.config.update({
        'TESTING': True,
        'SERVER_NAME': 'localhost',
        'APPLICATION_ROOT': '/',
        'PREFERRED_URL_SCHEME': 'http',
        'WTF_CSRF_ENABLED': False,  # Disable CSRF for testing
        'LOGIN_DISABLED': True  # Disable login requirement for testing
    })
    
    # Create a test database
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope='session')
def _db(app):
    """Provide the transactional boundaries around the tests."""
    db.app = app
    db.create_all()
    yield db
    db.session.remove()
    db.drop_all()

@pytest.fixture(scope='function')
def db_session(_db):
    """Creates a new database session for a test."""
    connection = _db.engine.connect()
    transaction = connection.begin()
    
    # Create a new session factory
    session_factory = sessionmaker(bind=connection)
    session = scoped_session(session_factory)
    _db.session = session
    
    yield session
    
    transaction.rollback()
    connection.close()
    session.remove()

@pytest.fixture(scope='function')
def client(app):
    """Create a test client for the app."""
    return app.test_client()

@pytest.fixture(scope='function')
def runner(app):
    """Create a test runner for the app's CLI commands."""
    return app.test_cli_runner()

@pytest.fixture(scope='function')
def test_user(db_session):
    """Create a test user."""
    user = User(
        username='test',
        email='test@example.com'
    )
    user.set_password('test123')
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture(scope='function')
def auth(client, test_user, app):
    """Create an AuthActions class for testing authentication."""
    class AuthActions:
        def __init__(self, client, test_user, app):
            self._client = client
            self._test_user = test_user
            self._app = app

        def login(self, username='test', password='test123'):
            # Make the login request
            response = self._client.post(
                '/auth/login',
                data={'username': username, 'password': password},
                follow_redirects=True
            )
            
            # Set up the session with Flask-Login's session key
            with self._client.session_transaction() as sess:
                sess['_user_id'] = str(self._test_user.id)
            
            return response

        def logout(self):
            return self._client.get('/auth/logout')

    return AuthActions(client, test_user, app) 