from .auth import auth_bp, profile_bp
from .activities import activities_bp, activity_api_bp
from .settings import settings_bp
from .entities import entities_bp, entity_api_bp
from .schedules import schedules_bp, schedule_api_bp
from .main import main_bp

__all__ = [
    'auth_bp',
    'profile_bp',
    'activities_bp',
    'activity_api_bp',
    'settings_bp',
    'entities_bp',
    'entity_api_bp',
    'schedules_bp',
    'schedule_api_bp',
    'main_bp'
] 