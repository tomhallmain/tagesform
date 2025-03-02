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
scheduler = BackgroundScheduler()

def create_app():
    """Application factory function"""
    app = Flask(__name__,
                template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates')),
                static_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), 'static')))

    # Configuration
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

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from .routes import (
        auth_bp, activities_bp, schedules_bp,
        entities_bp, settings_bp, main_bp
    )
    
    app.register_blueprint(main_bp)  # Main routes should be registered first
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(activities_bp, url_prefix='/activities')
    app.register_blueprint(schedules_bp, url_prefix='/schedules')
    app.register_blueprint(entities_bp, url_prefix='/entities')
    app.register_blueprint(settings_bp, url_prefix='/settings')

    # Initialize scheduler
    if config.is_main_werkzeug_process():
        from .tasks import init_scheduler
        init_scheduler(app, scheduler)

    # Debug logging
    if config.debug:
        logger.debug(f"Template folder: {app.template_folder}")
        logger.debug(f"Static folder: {app.static_folder}")
        logger.debug(f"Templates available: {os.listdir(app.template_folder)}")
        logger.debug(f"Static files available: {os.listdir(app.static_folder)}")

    return app 