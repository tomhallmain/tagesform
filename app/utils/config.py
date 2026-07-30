import os
from dotenv import load_dotenv
from ..utils.logging_setup import get_logger

# Load environment variables at module level
load_dotenv()

logger = get_logger(__name__)

class Config:
    def __init__(self):
        # Flask settings
        self.FLASK_APP = os.getenv('FLASK_APP', 'app.py')
        self.FLASK_ENV = os.getenv('FLASK_ENV', 'development')
        self.SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key-please-change')

        # Database settings
        self.DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///tagesform.db')
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False

        # UI Colors
        self.foreground_color = os.getenv('FOREGROUND_COLOR', 'white')
        self.background_color = os.getenv('BACKGROUND_COLOR', '#2596BE')

        # Debug mode
        self.debug = os.getenv('DEBUG', 'False').lower() == 'true'

        # Server settings
        self.server_port = int(os.getenv('SERVER_PORT', '6000'))
        self.server_host = os.getenv('SERVER_HOST', 'localhost')
        self.server_password = os.getenv('SERVER_PASSWORD', '')

        # OpenWeather settings
        self.open_weather_api_key = os.getenv('OPEN_WEATHER_API_KEY', '')
        self.open_weather_city = os.getenv('OPEN_WEATHER_CITY', 'Washington')

        # News API settings
        self.news_api_key = os.getenv('NEWS_API_KEY', '')
        self.news_api_source_trustworthiness = {
            'bbc-news': float(os.getenv('BBC_NEWS_TRUST', '0.5'))
        }

        # Ollama settings
        self.OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'deepseek-r1:14b')
        self.TASK_UPDATE_INTERVAL = int(os.getenv('TASK_UPDATE_INTERVAL', '24'))

        # How often the event cache (holidays/religious calendars) is refreshed
        # from the live upstream APIs. These change rarely in practice, so this
        # defaults to once a day rather than the every-few-hours cadence a
        # naive "keep it fresh" instinct might suggest -- the previous 3-hour
        # interval was needlessly hammering free, unauthenticated public APIs
        # for data that almost never changes that fast.
        self.EVENT_CACHE_UPDATE_INTERVAL = int(os.getenv('EVENT_CACHE_UPDATE_INTERVAL', '24'))

        # How often computed/deterministic calendar sources (Hebrew via
        # Hebcal; Coptic, once added) get backfilled. These aren't
        # "refreshed" in the usual sense -- their dates never change once
        # computed, so this job just tops up a rolling multi-year horizon and
        # is a no-op almost every time it runs. Kept as its own setting
        # (rather than reusing EVENT_CACHE_UPDATE_INTERVAL) since it's
        # conceptually a different kind of job with room to move to a much
        # longer interval later, independently of Nager's cadence.
        self.COMPUTED_CALENDAR_BACKFILL_INTERVAL = int(os.getenv('COMPUTED_CALENDAR_BACKFILL_INTERVAL', '24'))

        # How often the suggestion queue (dashboard "you might want to do
        # this" list) is recomputed per user.
        self.SUGGESTION_QUEUE_REFRESH_INTERVAL = int(os.getenv('SUGGESTION_QUEUE_REFRESH_INTERVAL', '6'))

        # Process settings
        self.is_main_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'

        # Validate critical settings
        self._validate_settings()

    def _validate_settings(self):
        """Validate critical configuration settings."""
        if not self.SECRET_KEY or self.SECRET_KEY == 'default-secret-key-please-change':
            logger.warning("WARNING: Using default SECRET_KEY. Please set a secure SECRET_KEY in production.")

        if not self.open_weather_api_key:
            logger.warning("OpenWeather API key not set. Weather functionality will be disabled.")
        
        if not self.news_api_key:
            logger.warning("News API key not set. News functionality will be disabled.")

    def is_main_werkzeug_process(self):
        """Check if we're running in the main Werkzeug process"""
        return self.is_main_process

# Create a singleton instance
config = Config()
