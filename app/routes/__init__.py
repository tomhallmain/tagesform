from .auth import auth_bp
from .activities import activities_bp
from .settings import settings_bp
from .entities import entities_bp
from .schedules import schedules_bp
from .main import main_bp

__all__ = [
    'auth_bp',
    'activities_bp',
    'settings_bp',
    'entities_bp',
    'schedules_bp',
    'main_bp'
] 