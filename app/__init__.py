from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
import os
from apscheduler.schedulers.background import BackgroundScheduler
from .utils.backup_config import backup_config
from .utils.config import config
from .utils.logging_setup import setup_logging, root_logger

# Initialize extensions
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Invalid username or password'
login_manager.login_message_category = 'error'
scheduler = BackgroundScheduler()

def create_app(config_name=None):
    """Application factory function"""
    app = Flask(__name__,
                template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')),
                static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'static')))

    # Configuration
    if config_name == 'testing':
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SECRET_KEY'] = 'test-secret-key'
        app.config['DEBUG'] = True
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    else:
        app.config['SECRET_KEY'] = config.SECRET_KEY
        app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URL
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = config.SQLALCHEMY_TRACK_MODIFICATIONS
        app.config['DEBUG'] = config.debug
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0 if config.debug else None

        # Set up logging
        setup_logging(app)
        
        # Create sample backup config if it doesn't exist
        if not backup_config.config_file.exists():
            backup_config.create_sample_config()

    # Initialize extensions with app
    from .models import db, User
    db.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    # Register custom filters
    from .utils.filters import title_case, format_rating
    app.jinja_env.filters['title_case'] = title_case
    app.jinja_env.filters['format_rating'] = format_rating
    
    # Register translation function for templates
    from .utils.translations import I18N, _
    app.jinja_env.globals['_'] = _
    
    # Add context processor for locale information
    @app.context_processor
    def inject_locale():
        return dict(current_locale=I18N.get_current_locale())

    # I18N.get_current_locale()/get_current_translation() cache their result
    # on flask.g so a request doesn't re-resolve the locale on every _()
    # call. g is normally fresh per request, so this is usually a no-op --
    # but anything that keeps an app context alive across multiple requests
    # (e.g. this app's own test suite, which pushes one app context for the
    # whole session) would otherwise leak one request's resolved locale into
    # the next. Clearing it explicitly at request start keeps locale
    # resolution correctly scoped to a single request regardless.
    @app.before_request
    def reset_locale_cache():
        I18N.reset_locale_cache()

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from .routes import (
        auth_bp, profile_bp, activities_bp, activity_api_bp,
        schedules_bp, schedule_api_bp, entities_bp, entity_api_bp,
        settings_bp, suggestions_api_bp, main_bp
    )

    app.register_blueprint(main_bp)  # Main routes should be registered first
    app.register_blueprint(auth_bp)  # Auth routes at root level
    app.register_blueprint(profile_bp, url_prefix='/profile')  # Profile routes under /profile
    app.register_blueprint(activities_bp)  # Activity pages at root level
    app.register_blueprint(activity_api_bp)  # Activity API routes under /api
    app.register_blueprint(schedules_bp)  # Schedule pages at root level
    app.register_blueprint(schedule_api_bp)  # Schedule API routes under /api
    app.register_blueprint(entities_bp)  # Entity pages at root level
    app.register_blueprint(entity_api_bp)  # Entity API routes under /api
    app.register_blueprint(settings_bp, url_prefix='/settings')  # Settings remain under /settings
    app.register_blueprint(suggestions_api_bp)  # Suggestion queue API routes under /api/suggestions

    # Register `flask gazetteer-load` / `flask geocode-backfill` -- see
    # docs/entity-geolocation.md.
    from .cli import register_cli
    register_cli(app)

    # Initialize scheduler only for non-testing environments
    if config_name != 'testing' and config.is_main_werkzeug_process():
        from .tasks import init_scheduler
        init_scheduler(app, scheduler)

    # Debug logging
    if config.debug:
        root_logger.debug(f"Template folder: {app.template_folder}")
        root_logger.debug(f"Static folder: {app.static_folder}")
        root_logger.debug(f"Templates available: {os.listdir(app.template_folder)}")
        root_logger.debug(f"Static files available: {os.listdir(app.static_folder)}")

    return app 