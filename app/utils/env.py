import os
from pathlib import Path


def get_app_data_dir():
    """Get the application data directory based on the operating system"""
    try:
        if os.name == 'nt':  # Windows
            app_data = os.getenv('APPDATA')
            if not app_data:
                raise EnvironmentError("APPDATA environment variable not found")
            app_dir = Path(app_data) / 'tagesform'
        else:  # Linux/Mac
            home = Path.home()
            app_dir = home / '.local' / 'share' / 'tagesform'
        
        # Create directory if it doesn't exist
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir
        
    except Exception:
        raise

def get_logs_dir():
    """Get the logs directory path"""
    try:
        logs_dir = get_app_data_dir() / 'logs'
        logs_dir.mkdir(exist_ok=True)
        return logs_dir
        
    except Exception:
        raise

def get_config_dir():
    """Get the configuration directory path"""
    try:
        config_dir = get_app_data_dir() / 'config'
        config_dir.mkdir(exist_ok=True)
        return config_dir
        
    except Exception:
        raise