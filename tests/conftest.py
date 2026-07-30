"""
Root conftest for the Tagesform test suite.

IMPORTANT: The env vars below must be set at module load time -- before any
`app` module is imported -- because `app_info_cache`, `backup_config`, and
`config` are all module-level singletons instantiated on first import (and
`config` loads `.env` via python-dotenv, which does not override already-set
env vars). Any nested conftest.py files (tests/unit/, tests/integration/)
must mirror this same module-level bootstrap for the same reason -- pytest
may load a nested conftest.py before this one runs, depending on collection
order.
"""

import atexit
import os
import shutil
import sys
import tempfile

# Add the project root directory to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Bootstrap safe temporary locations so that the singletons created during
# initial import of `app` never touch the real cache/config files or the
# developer's real .env-configured external services.
_bootstrap_tmp = tempfile.mkdtemp(prefix="tagesform_tests_")
os.environ["TAGESFORM_CACHE_DIR"] = os.path.join(_bootstrap_tmp, "cache")
os.environ["TAGESFORM_CONFIG_DIR"] = os.path.join(_bootstrap_tmp, "config")
os.environ["TAGESFORM_DATA_DIR"] = os.path.join(_bootstrap_tmp, "data")
os.makedirs(os.environ["TAGESFORM_CACHE_DIR"], exist_ok=True)
os.makedirs(os.environ["TAGESFORM_CONFIG_DIR"], exist_ok=True)
os.makedirs(os.environ["TAGESFORM_DATA_DIR"], exist_ok=True)
atexit.register(shutil.rmtree, _bootstrap_tmp, True)

# Deterministic, obviously-fake values for the external-service settings
# Config() reads via os.getenv -- so tests never depend on (or leak) whatever
# real API keys/hosts happen to be in the developer's .env.
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["OPEN_WEATHER_API_KEY"] = "test-openweather-key"
os.environ["OPEN_WEATHER_CITY"] = "Testville"
os.environ["NEWS_API_KEY"] = "test-news-key"
os.environ["BBC_NEWS_TRUST"] = "0.5"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"  # deliberately unreachable
os.environ["OLLAMA_MODEL"] = "test-model"

import pytest
from flask import Flask, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, login_user
from sqlalchemy.orm import scoped_session, sessionmaker
import warnings

# Now we can import from app
from app import create_app
from app.models import User, db

# Filter out specific deprecation warnings
warnings.filterwarnings('ignore', category=DeprecationWarning, 
                       message="'werkzeug.urls.url_decode' is deprecated")
warnings.filterwarnings('ignore', category=DeprecationWarning, 
                       message="'werkzeug.urls.url_encode' is deprecated")
warnings.filterwarnings('ignore', category=DeprecationWarning,
                       message="The Query.get() method is considered legacy")


def repoint_singleton_bindings(monkeypatch, attr_name, old_obj, new_obj):
    """Repoint every imported module's module-level binding of *old_obj* to
    *new_obj* (undone automatically by monkeypatch at test teardown).

    Modules that do e.g. `from ..utils.app_info_cache import app_info_cache`
    at module level hold their own reference to the singleton, so patching
    only the source module (app.utils.app_info_cache) leaves those other
    bindings stale -- they'd keep pointing at whatever instance existed when
    they were first imported. Sweeping sys.modules retires that whack-a-mole:
    the identity comparison guarantees only bindings to the exact old object
    are touched.
    """
    for module in list(sys.modules.values()):
        try:
            if getattr(module, attr_name, None) is old_obj:
                monkeypatch.setattr(module, attr_name, new_obj)
        except Exception:
            continue


@pytest.fixture(autouse=True)
def isolated_singletons(tmp_path, monkeypatch):
    """Re-initialise the app_info_cache, backup_config, and config singletons
    for each test, pointing at a fresh per-test temp directory.

    The module-level env var bootstrap above keeps the *first* import of
    these singletons off the real cache/config files, but they're still
    module-level singletons created once per process -- without this, a test
    that mutates one (e.g. app_info_cache.set(...)) would leak that state
    into every later test in the same session. Recreating them per test, and
    repointing every module's reference to the new instance, keeps tests
    isolated from each other as well as from the real environment.
    """
    cache_dir = tmp_path / "cache"
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    cache_dir.mkdir()
    config_dir.mkdir()
    data_dir.mkdir()

    monkeypatch.setenv("TAGESFORM_CACHE_DIR", str(cache_dir))
    monkeypatch.setenv("TAGESFORM_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("TAGESFORM_DATA_DIR", str(data_dir))

    import app.utils.app_info_cache as aic
    import app.utils.backup_config as bc
    import app.utils.config as cfg

    repoint_singleton_bindings(monkeypatch, "app_info_cache", aic.app_info_cache, aic.AppInfoCache())
    repoint_singleton_bindings(monkeypatch, "backup_config", bc.backup_config, bc.BackupConfig())
    repoint_singleton_bindings(monkeypatch, "config", cfg.config, cfg.Config())

    yield


# As of this writing, nothing else in the app carries class-level mutable
# state that would leak between tests (checked: SchedulesManager.last_set_schedule
# is dead -- never assigned past its `None` declaration -- and TempDir isn't
# imported anywhere under app/). isolated_singletons above covers the only
# singletons that actually need it. If code is ever added with a similar
# setup -- a class-level list/dict/reference that a request handler or
# service mutates and that should not survive past a single test -- uncomment
# this, fill in the reset(s) following the same pattern as _reset() below,
# and register it as an autouse fixture like isolated_singletons.
#
# @pytest.fixture(autouse=True)
# def reset_app_globals():
#     """Reset class-level mutable state not covered by isolated_singletons.
#
#     Runs before each test so state leaked by a previous test doesn't
#     pollute the next one; teardown after yield is a courtesy reset so a
#     failing test leaves the process clean for any post-run inspection.
#     """
#     def _reset():
#         # Example -- fill in real attributes as they're added:
#         # try:
#         #     from app.services.schedules_manager import SchedulesManager
#         #     SchedulesManager.last_set_schedule = None
#         # except Exception:
#         #     pass
#         pass
#
#     _reset()
#     yield
#     _reset()


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
        'LOGIN_DISABLED': False  # Enable login protection for testing
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
                '/login',  # Updated path
                data={'username': username, 'password': password},
                follow_redirects=True
            )
            return response

        def logout(self):
            return self._client.get('/logout', follow_redirects=True)

    return AuthActions(client, test_user, app)

@pytest.fixture(autouse=True)
def cleanup_session(client):
    """Clean up the session after each test."""
    yield
    # Clear session and log out after each test
    with client.session_transaction() as sess:
        sess.clear()
    client.get('/logout', follow_redirects=True) 