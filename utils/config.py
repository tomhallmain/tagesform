import os
from dotenv import load_dotenv
from utils.utils import Utils

# Load environment variables at module level
load_dotenv()

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

        # Process settings
        self.is_main_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'

        # Validate critical settings
        self._validate_settings()

    def _validate_settings(self):
        """Validate critical configuration settings."""
        if not self.SECRET_KEY or self.SECRET_KEY == 'default-secret-key-please-change':
            Utils.log_yellow("WARNING: Using default SECRET_KEY. Please set a secure SECRET_KEY in production.")

        if not self.open_weather_api_key:
            Utils.log_yellow("OpenWeather API key not set. Weather functionality will be disabled.")
        
        if not self.news_api_key:
            Utils.log_yellow("News API key not set. News functionality will be disabled.")

    def is_main_werkzeug_process(self):
        """Check if we're running in the main Werkzeug process"""
        return self.is_main_process

# Create a singleton instance
config = Config()
