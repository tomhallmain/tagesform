from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from .utils.config import config

# Set up logging based on debug mode
logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

    # Initialize extensions with app
    from .models import db, User
    db.init_app(app)
    login_manager.init_app(app)
    Migrate(app, db)

    # Register custom filters
    from .utils.filters import title_case, format_rating
    app.jinja_env.filters['title_case'] = title_case
    app.jinja_env.filters['format_rating'] = format_rating

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from .routes import (
        auth_bp, profile_bp, activities_bp, activity_api_bp,
        schedules_bp, schedule_api_bp, entities_bp, entity_api_bp,
        settings_bp, main_bp
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

    # Initialize scheduler only for non-testing environments
    if config_name != 'testing' and config.is_main_werkzeug_process():
        from .tasks import init_scheduler
        init_scheduler(app, scheduler)

    # Debug logging
    if config.debug:
        logger.debug(f"Template folder: {app.template_folder}")
        logger.debug(f"Static folder: {app.static_folder}")
        logger.debug(f"Templates available: {os.listdir(app.template_folder)}")
        logger.debug(f"Static files available: {os.listdir(app.static_folder)}")

    return app 