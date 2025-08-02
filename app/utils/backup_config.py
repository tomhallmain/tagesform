import json
import os
from pathlib import Path
from ..utils.logging_setup import get_logger
from .env import get_app_data_dir

logger = get_logger('backup_config')

class BackupConfig:
    def __init__(self):
        self.config_file = Path('backup_config.json')
        self.config = self._load_config()
    
    def _load_config(self):
        """Load backup configuration from JSON file"""
        default_config = {
            'backup_directory': None,  # Will use app data directory if None
            'backup_directory_secondary': None,  # Optional second backup location
            'max_backups': 10,
            'backup_interval_hours': 24
        }
        
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Loaded backup config from {self.config_file}")
                    return {**default_config, **config}
            else:
                logger.info("No backup config file found, using defaults")
                return default_config
                
        except Exception as e:
            logger.error(f"Error loading backup config: {e}")
            return default_config
    
    def get_backup_directory(self):
        """Get the primary backup directory path"""
        if self.config.get('backup_directory'):
            backup_dir = Path(self.config['backup_directory'])
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Using custom backup directory: {backup_dir}")
                return backup_dir
            except Exception as e:
                logger.error(f"Error creating custom backup directory {backup_dir}: {e}")
                logger.info("Falling back to app data directory")
        
        # Fall back to app data directory
        app_data_dir = get_app_data_dir()
        backup_dir = app_data_dir / 'backups'
        backup_dir.mkdir(exist_ok=True)
        logger.info(f"Using app data backup directory: {backup_dir}")
        return backup_dir
    
    def get_secondary_backup_directory(self):
        """Get the secondary backup directory path (returns None if not configured)"""
        if self.config.get('backup_directory_secondary'):
            backup_dir = Path(self.config['backup_directory_secondary'])
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Using secondary backup directory: {backup_dir}")
                return backup_dir
            except Exception as e:
                logger.error(f"Error creating secondary backup directory {backup_dir}: {e}")
                logger.info("Secondary backup directory not available")
                return None
        return None
    
    def get_max_backups(self):
        """Get maximum number of backups to keep"""
        return self.config.get('max_backups', 10)
    
    def get_backup_interval_hours(self):
        """Get backup interval in hours"""
        return self.config.get('backup_interval_hours', 24)
    
    def create_sample_config(self):
        """Create a sample configuration file"""
        sample_config = {
            "backup_directory": "D:/tagesform/backups",
            "backup_directory_secondary": None,
            "max_backups": 10,
            "backup_interval_hours": 24,
            "_comment": "backup_directory: Path to primary backup directory (use forward slashes, set to null to use app data directory)",
            "_comment2": "backup_directory_secondary: Path to secondary backup directory (optional, set to null to disable)",
            "_comment3": "max_backups: Maximum number of backups to keep",
            "_comment4": "backup_interval_hours: How often to create backups (in hours)",
            "_example": "Example: 'C:/backups/tagesform' or '/home/user/backups/tagesform'"
        }
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(sample_config, f, indent=2)
            logger.info(f"Created sample backup config: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"Error creating sample config: {e}")
            return False

# Create a singleton instance
backup_config = BackupConfig() 