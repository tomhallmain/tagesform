from flask import Blueprint, render_template, jsonify
from flask_login import current_user, login_required
from ..services.integration_service import integration_service
from ..models import Activity, Schedule, Entity

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        dashboard_data = integration_service.get_dashboard_data()
        return render_template('index.html', dashboard_data=dashboard_data)
    return render_template('index.html')

@main_bp.route('/api/stats')
@login_required
def get_stats():
    """Get statistics for the dashboard"""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    return jsonify({
        'weekly_count': Activity.query.filter(
            Activity.scheduled_time >= now,
            Activity.scheduled_time <= now + timedelta(weeks=1)
        ).count(),
        'schedule_count': Schedule.query.count(),
        'places_count': Entity.query.count()
    })

@main_bp.route('/health')
def health_check():
    """Health check endpoint that also verifies Ollama connection"""
    import requests
    from ..services.ollama_service import ollama_service
    from ..models import db
    from ..utils.config import config

    try:
        ollama_status = "connected" if ollama_service.check_connection() else "error"
    except requests.exceptions.RequestException:
        ollama_status = "unavailable"

    return jsonify({
        'status': 'healthy',
        'ollama_status': ollama_status,
        'database': 'connected' if db.engine.execute('SELECT 1').scalar() else 'error',
        'model': config.OLLAMA_MODEL
    }) 