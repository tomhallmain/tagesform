from datetime import datetime
from ..models import db
from ..routes.entities import ImportData

def cleanup_expired_imports():
    """Remove expired import data from the database"""
    try:
        # Delete all expired imports
        expired_count = ImportData.query.filter(
            ImportData.expires_at <= datetime.utcnow()
        ).delete()
        
        db.session.commit()
        print(f"Cleaned up {expired_count} expired imports")
        
    except Exception as e:
        db.session.rollback()
        print(f"Error cleaning up expired imports: {str(e)}") 