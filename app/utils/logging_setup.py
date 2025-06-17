import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from .custom_formatter import CustomFormatter
from .env import get_logs_dir

def _cleanup_old_logs(log_dir: Path, logger: logging.Logger) -> None:
    """
    Clean up log files that are older than 30 days if there are more than 10 log files.
    
    Args:
        log_dir: Path object pointing to the directory containing log files
        logger: Logger instance to use for logging cleanup operations
    """
    try:
        log_files: List[Path] = list(log_dir.glob('tagesform_*.log'))
        if len(log_files) <= 10:
            return

        current_time: datetime = datetime.now()
        cutoff_date: datetime = current_time - timedelta(days=30)
        
        for log_file in log_files:
            try:
                # Extract date from filename (format: tagesform_YYYY-MM-DD.log)
                date_str: str = log_file.stem.split('_')[-1]
                file_date: datetime = datetime.strptime(date_str, '%Y-%m-%d')
            except (ValueError, IndexError):
                # If filename doesn't contain a valid date, use the file's last modified date
                file_date = datetime.fromtimestamp(log_file.stat().st_mtime)
            
            if file_date < cutoff_date:
                log_file.unlink()
                logger.debug(f"Deleted old log file: {log_file}")
    except Exception as e:
        logger.error(f"Error cleaning up old log files: {e}")

def setup_logging(app=None):
    """
    Set up logging for the Flask application.
    
    Args:
        app: Optional Flask application instance. If provided, configures Flask's logger.
    """
    # Get log directory using env utility
    log_dir = get_logs_dir()

    # Clean up old logs before creating new one
    root_logger = logging.getLogger()
    _cleanup_old_logs(log_dir, root_logger)

    # Create daily log file
    date_str: str = datetime.now().strftime("%Y-%m-%d")
    log_file: Path = log_dir / f'tagesform_{date_str}.log'

    # Configure root logger
    root_logger.setLevel(logging.DEBUG)
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(CustomFormatter())
    root_logger.addHandler(console_handler)

    # Add file handler
    file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(CustomFormatter())
    root_logger.addHandler(file_handler)

    # Configure Flask logger if app is provided
    if app:
        app.logger.setLevel(logging.DEBUG)
        # Prevent propagation to root logger
        app.logger.propagate = False
        # Remove any existing handlers
        for handler in app.logger.handlers[:]:
            app.logger.removeHandler(handler)
        # Add our handlers
        app.logger.addHandler(console_handler)
        app.logger.addHandler(file_handler)
        app.logger.info('Tagesform startup')

def get_logger(module_name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        module_name: The name of the module requesting the logger
        
    Returns:
        A configured logger instance for the module
    """
    return logging.getLogger(f"tagesform.{module_name}")

# Initialize root logger
root_logger: logging.Logger = logging.getLogger("tagesform") 
