import os
import shutil
from datetime import datetime
from pathlib import Path
from flask import current_app
from sqlalchemy import create_engine, text
from ..utils.logging_setup import get_logger
from ..utils.backup_config import backup_config

logger = get_logger('backup_service')

class BackupService:
    def __init__(self, db_uri=None):
        self.db_uri = db_uri or current_app.config['SQLALCHEMY_DATABASE_URI']
        self.backup_dir = backup_config.get_backup_directory()
        self.backup_dir_secondary = backup_config.get_secondary_backup_directory()
        self.max_backups = backup_config.get_max_backups()
    
    def create_backup(self, backup_name=None):
        """Create a backup of the database"""
        try:
            if not backup_name:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_name = f"tagesform_backup_{timestamp}.db"
            
            # For SQLite, we can simply copy the database file
            if 'sqlite' in self.db_uri.lower():
                db_path = self.db_uri.replace('sqlite:///', '')
                if not os.path.isabs(db_path):
                    # Handle relative paths
                    db_path = os.path.join(os.getcwd(), db_path)
                
                # Create primary backup
                backup_path = self.backup_dir / backup_name
                shutil.copy2(db_path, backup_path)
                logger.info(f"Primary database backup created: {backup_path}")
                
                # Create secondary backup if configured
                if self.backup_dir_secondary:
                    backup_path_secondary = self.backup_dir_secondary / backup_name
                    shutil.copy2(db_path, backup_path_secondary)
                    logger.info(f"Secondary database backup created: {backup_path_secondary}")
                
                return str(backup_path)
            else:
                # For other databases, we'd need to implement different backup strategies
                logger.error("Backup not implemented for non-SQLite databases")
                return None
                
        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}")
            raise
    
    def restore_backup(self, backup_path):
        """Restore database from backup"""
        try:
            if not os.path.exists(backup_path):
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
            # For SQLite, we can simply copy the backup file back
            if 'sqlite' in self.db_uri.lower():
                db_path = self.db_uri.replace('sqlite:///', '')
                if not os.path.isabs(db_path):
                    db_path = os.path.join(os.getcwd(), db_path)
                
                # Create a backup of current database before restoring
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                current_backup = f"{db_path}.pre_restore_{timestamp}"
                shutil.copy2(db_path, current_backup)
                logger.info(f"Current database backed up before restore: {current_backup}")
                
                # Restore from backup
                shutil.copy2(backup_path, db_path)
                logger.info(f"Database restored from: {backup_path}")
                return True
            else:
                logger.error("Restore not implemented for non-SQLite databases")
                return False
                
        except Exception as e:
            logger.error(f"Error restoring backup: {str(e)}")
            raise
    
    def list_backups(self):
        """List all available backups from both locations"""
        try:
            backups = []
            
            # Get backups from primary location
            for backup_file in self.backup_dir.glob('*.db'):
                stat = backup_file.stat()
                backups.append({
                    'name': backup_file.name,
                    'path': str(backup_file),
                    'location': 'primary',
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_ctime),
                    'modified': datetime.fromtimestamp(stat.st_mtime)
                })
            
            # Get backups from secondary location
            if self.backup_dir_secondary:
                for backup_file in self.backup_dir_secondary.glob('*.db'):
                    stat = backup_file.stat()
                    backups.append({
                        'name': backup_file.name,
                        'path': str(backup_file),
                        'location': 'secondary',
                        'size': stat.st_size,
                        'created': datetime.fromtimestamp(stat.st_ctime),
                        'modified': datetime.fromtimestamp(stat.st_mtime)
                    })
            
            # Sort by creation date (newest first)
            backups.sort(key=lambda x: x['created'], reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"Error listing backups: {str(e)}")
            return []
    
    def cleanup_old_backups(self, keep_count=None):
        """Remove old backups from both locations, keeping only the specified number"""
        if keep_count is None:
            keep_count = self.max_backups
            
        try:
            backups = self.list_backups()
            if len(backups) > keep_count:
                backups_to_remove = backups[keep_count:]
                removed_count = 0
                
                for backup in backups_to_remove:
                    try:
                        os.remove(backup['path'])
                        logger.info(f"Removed old backup: {backup['name']} from {backup['location']}")
                        removed_count += 1
                    except Exception as e:
                        logger.error(f"Error removing backup {backup['name']}: {e}")
                
                logger.info(f"Cleaned up {removed_count} old backups")
                return removed_count
            return 0
            
        except Exception as e:
            logger.error(f"Error cleaning up old backups: {str(e)}")
            return 0

# Lazy singleton pattern
_backup_service_instance = None

def get_backup_service():
    """Get the backup service instance, creating it if necessary"""
    global _backup_service_instance
    if _backup_service_instance is None:
        _backup_service_instance = BackupService()
    return _backup_service_instance 